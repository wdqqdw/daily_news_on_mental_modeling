"""Primary metadata discovery for the publication-grouped research library."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import copy
import xml.etree.ElementTree as ET
import urllib.request
import json
import re
import threading
import time
import urllib.error
import urllib.parse
from core import date_floor, keys
from library_core import JOURNALS, classify
from sources import fetch, clean, get_acl, BAD, TARGET, off_scope_reason, topic, score, AGENT

HUMAN = re.compile(r'\b(human|people|person|participants?|cogniti\w*|mental\w*|emoti\w*|empath\w*|belief\w*|intent\w*|social|hippocamp\w*|brain|concept\w* learning)\b', re.I)
SUBJECT = re.compile(TARGET.pattern + r'|cognitive map|relational memory|human learning|human reading|social navigation|hippocampus|hippocampal|world models?|generative agents|humanoid agents|social interaction|affect control|inverse planning|mental world|human simulation|human digital twin', re.I)
CROSSREF_LOCK = threading.Lock()

def eligible(p, today):
    abstract = p.get('_abstract', '')
    try:
        age = (today - date_floor(p['published'])).days
    except (ValueError, KeyError):
        return False
    return (p.get('status') in ('published','preprint') and classify(p['venue']) is not None
            and age >= 0 and not BAD.search(p['title']) and not off_scope_reason(p)
            and len(abstract.split()) >= 55 and bool(SUBJECT.search(p['title'] + ' ' + abstract[:700]))
            and bool(HUMAN.search(p['title'] + ' ' + abstract)))

def normalize_venue(name):
    # Crossref names official proceedings differently from ACL's concise names.
    aliases = {'Proceedings of the AAAI Conference on Artificial Intelligence': 'AAAI',
               'Proceedings of the International Joint Conference on Artificial Intelligence': 'IJCAI'}
    return aliases.get(name, name)

def crossref_rows(items, today):
    out = []
    for x in items:
        if x.get('type') not in ('journal-article', 'proceedings-article') or not x.get('DOI'):
            continue
        if any(u.get('type') in ('retraction', 'withdrawal') for u in x.get('update-to', [])):
            continue
        dates = []
        for key in ('published-online', 'published-print', 'published', 'issued'):
            parts = x.get(key, {}).get('date-parts', [[]])[0]
            if 1 <= len(parts) <= 3:
                value = '-'.join(str(n) if i == 0 else f'{n:02}' for i, n in enumerate(parts))
                try:
                    date_floor(value); dates.append(value)
                except ValueError:
                    pass
        if not dates:
            continue
        authors = x.get('author', []); first = authors[0] if authors else {}
        doi = x['DOI'].lower()
        p = {'title': clean(' '.join(x.get('title', []))), '_abstract': clean(x.get('abstract', '')),
             'doi': doi, 'url': 'https://doi.org/' + doi,
             'venue': normalize_venue(clean(' '.join(x.get('container-title', [])))),
             'published': min(dates, key=date_floor), 'status': 'published',
             'authors': (first.get('given', '') + ' ' + first.get('family', first.get('name', 'Authors in paper'))).strip() + (' et al.' if len(authors) > 1 else ''),
             'citations': x.get('is-referenced-by-count', 0), 'metadata_source': 'Crossref',
             'summary_source': 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')}
        if eligible(p, today):
            out.append(p)
    return out

def crossref(query, today, issn=None, start_date=None, end_date=None, offset=0):
    params = {'query': query, 'filter': f'from-pub-date:{start_date or today-dt.timedelta(days=365)},until-pub-date:{end_date or today}',
              'rows': 70, 'offset': offset, 'select': 'DOI,title,author,container-title,published-online,published-print,published,issued,type,is-referenced-by-count,abstract,update-to'}
    endpoint = f'journals/{issn}/works' if issn else 'works'
    # Pace this shared public API rather than fan out journal requests at once.
    with CROSSREF_LOCK:
        for attempt in range(3):
            try:
                data = json.loads(fetch('https://api.crossref.org/' + endpoint + '?' + urllib.parse.urlencode(params)))
                break
            except urllib.error.HTTPError as ex:
                if ex.code != 429 or attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        time.sleep(1.1)
    return crossref_rows(data['message']['items'], today), int(data['message'].get('total-results',0))

# Complementary topic queries rotate through the older literature by relevance.
ARXIV_THEMES = {
 'world': ['social world model','mental world model','emotional world model','human world model','generative agents','human simulation','mental simulation'],
 'emotion': ['emotion modeling','emotion modelling','emotional intelligence','affective computing','cognitive appraisal','empathy modeling','affect control','emotion recognition','emotion reasoning','emotional dynamics'],
 'mind': ['theory of mind','mental state inference','belief tracking','inverse planning','human intention','goal inference','mental state modeling'],
 'person': ['personality modeling','personality simulation','psychological model','mental health simulation','patient simulation','human digital twin'],
 'cognition': ['human cognitive model','cognitive map','human decision making','human memory model','resource rational','social cognition'],
 'social': ['social simulation','social agents','human behavior modeling','social reasoning','interpersonal relationship','human preference learning'],
}
ARXIV_LOCK = threading.Lock()
DATACITE_LOCK = threading.Lock()
NS = {'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom','o':'http://a9.com/-/spec/opensearch/1.1/'}

def arxiv_rows(content, today):
    root = ET.fromstring(content); out = []
    for entry in root.findall('a:entry', NS):
        def value(key):
            return clean(entry.findtext(key, default='', namespaces=NS))
        match = re.search(r'arxiv\.org/abs/(.+?)(?:v\d+)?$', value('a:id'))
        if not match:
            if '/api/errors' in value('a:id'):
                raise ValueError('arXiv API error: ' + value('a:summary'))
            continue
        aid = match[1]; abstract = value('a:summary')
        if re.search(r'withdrawn|retracted', value('x:comment') + ' ' + abstract[:250], re.I):
            continue
        url = 'https://arxiv.org/abs/' + aid
        authors = [clean(a.findtext('a:name', default='', namespaces=NS)) for a in entry.findall('a:author', NS)]
        p = {'title':value('a:title'), '_abstract':abstract, 'url':url, 'pdf':'https://arxiv.org/pdf/'+aid,
             'doi':'10.48550/arXiv.'+aid, 'doi_aliases':[value('x:doi')] if value('x:doi') else [],
             'published':value('a:published')[:10], 'authors':authors[0]+(' et al.' if len(authors)>1 else '') if authors else 'Authors in paper',
             'venue':'arXiv', 'status':'preprint', 'metadata_source':'arXiv API', 'summary_source':url,
             'arxiv_id':aid, 'arxiv_version':value('a:id').rsplit('/',1)[-1], 'arxiv_updated':value('a:updated')[:10]}
        # Author-supplied journal references are provenance, not independent acceptance verification.
        if value('x:journal_ref'):
            p['author_journal_reference'] = value('x:journal_ref')
        if eligible(p, today):
            out.append(p)
    total = int(root.findtext('o:totalResults', default=str(len(root.findall('a:entry',NS))), namespaces=NS))
    return out, total

def arxiv_query(terms, today, lane='recent', start=0):
    query = '(' + ' OR '.join('(ti:"'+term+'" OR abs:"'+term+'")' for term in terms) + ')'
    cutoff = today - dt.timedelta(days=365)
    date_range = (cutoff.strftime('%Y%m%d')+'0000 TO '+today.strftime('%Y%m%d')+'2359') if lane=='recent' else ('199101010000 TO '+(cutoff-dt.timedelta(days=1)).strftime('%Y%m%d')+'2359')
    params = {'search_query':query+' AND submittedDate:['+date_range+']', 'start':start, 'max_results':60,
              'sortBy':'submittedDate' if lane=='recent' else 'relevance', 'sortOrder':'descending'}
    return 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode(params)

def get_arxiv(terms, today, lane='recent', start=0):
    url = arxiv_query(terms, today, lane, start)
    # arXiv asks for one connection and at least three seconds between requests.
    with ARXIV_LOCK:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':AGENT}),timeout=40) as response:
                    content = response.read(12_000_000).decode()
                break
            except urllib.error.HTTPError as ex:
                if ex.code not in (408, 429, 500, 502, 503, 504):
                    detail = clean(ex.read(2000).decode('utf-8', errors='replace'))
                    raise RuntimeError(f'arXiv HTTP {ex.code}: {detail[:500]}') from ex
                if attempt==2:
                    raise
                time.sleep(4*(attempt+1))
            except (OSError, urllib.error.URLError):
                if attempt==2:
                    raise
                time.sleep(4*(attempt+1))
            finally:
                time.sleep(3.1)
    return arxiv_rows(content, today)

def datacite_arxiv_rows(items, today, lane):
    """Read arXiv-deposited DOI metadata, never DOI registration dates as publication."""
    out=[]; cutoff=today-dt.timedelta(days=365)
    for item in items:
        x=item.get('attributes',{}); doi=x.get('doi','')
        match=re.fullmatch(r'10\.48550/arxiv\.(.+)',doi,re.I)
        if not match or x.get('state')!='findable':continue
        aid=match[1]; url='https://arxiv.org/abs/'+aid
        landing=urllib.parse.urlsplit(x.get('url',''))
        if landing.hostname not in ('arxiv.org','www.arxiv.org') or landing.path.lower()!='/abs/'+aid.lower():continue
        descriptions=x.get('descriptions',[])
        abstract=clean(' '.join(d.get('description','') for d in descriptions if d.get('descriptionType')=='Abstract'))
        if re.search(r'withdrawn|retracted', ' '.join(d.get('description','') for d in descriptions), re.I):continue
        dates={}
        for entry in x.get('dates',[]):
            date=entry.get('date','')[:10]
            try:date_floor(date)
            except ValueError:continue
            dates.setdefault(entry.get('dateType'),[]).append(date)
        published=min(dates.get('Submitted') or dates.get('Available') or dates.get('Issued') or [str(x.get('publicationYear',''))],key=date_floor)
        if (date_floor(published)>=cutoff)!=(lane=='recent'):continue
        creators=x.get('creators',[])
        aliases=[r['relatedIdentifier'] for r in x.get('relatedIdentifiers',[]) if r.get('relatedIdentifierType')=='DOI' and r.get('relationType') in ('IsVersionOf','IsIdenticalTo')]
        p={'title':clean(' '.join(t.get('title','') for t in x.get('titles',[]))), '_abstract':abstract,
           'url':url,'pdf':'https://arxiv.org/pdf/'+aid,'doi':doi,'doi_aliases':aliases,
           'published':published,'authors':creators[0]['name']+(' et al.' if len(creators)>1 else '') if creators else 'Authors in paper',
           'venue':'arXiv','status':'preprint','metadata_source':'arXiv / DataCite',
           'summary_source':'https://api.datacite.org/dois/'+urllib.parse.quote(doi,safe=''),
           'arxiv_id':aid,'arxiv_updated':max(dates.get('Updated') or [published],key=date_floor)}
        if eligible(p,today):out.append(p)
    return out

def get_datacite_arxiv(terms,today,lane='recent',start=0):
    cutoff=today-dt.timedelta(days=365)
    phrases=' OR '.join('(titles.title:"'+term+'" OR descriptions.description:"'+term+'")' for term in terms)
    years=f'{cutoff.year} TO {today.year}' if lane=='recent' else f'1991 TO {cutoff.year}'
    params={'prefix':'10.48550','query':'('+phrases+') AND publicationYear:['+years+']',
            'page[size]':60,'page[number]':start//60+1}
    if lane=='recent':params['sort']='-published'
    with DATACITE_LOCK:
        try:
            data=json.loads(fetch('https://api.datacite.org/dois?'+urllib.parse.urlencode(params)))
        finally:time.sleep(1.1)
    return datacite_arxiv_rows(data['data'],today,lane),int(data['meta']['total'])

def discover_arxiv(terms,today,lane='recent',start=0,datacite_start=0):
    try:
        rows,total=get_arxiv(terms,today,lane,start)
        return rows,total,'arxiv',None
    except (OSError,ValueError,RuntimeError,ET.ParseError) as ex:
        # DataCite is arXiv's public DOI registry, with its own API and deposited abstracts.
        # Keep independent pagination because the two services order results differently.
        rows,total=get_datacite_arxiv(terms,today,lane,datacite_start)
        return rows,total,'datacite',str(ex)[:300]

def collect(today, state=None):
    state = copy.deepcopy(state or {'version':1,'pages':{},'reviews':{}})
    pages = state.setdefault('pages', {}); tasks = []; date_index = today.toordinal()
    themes = list(ARXIV_THEMES); cutoff = today-dt.timedelta(days=365)
    # Search every recent theme, plus three independently paged historical topics.
    for theme in themes:
        tasks.append(('arXiv recent '+theme,discover_arxiv,(ARXIV_THEMES[theme],today,'recent',0),'recent',None))
    for i in range(3):
        theme = themes[(date_index*3+i)%len(themes)]; key = 'arxiv:'+theme
        tasks.append(('arXiv history '+theme,discover_arxiv,(ARXIV_THEMES[theme],today,'history',pages.get(key,0),pages.get('datacite:'+theme,0)),'history',key))
    journal_items = list(JOURNALS.items())
    for name, issn in journal_items:
        tasks.append(('Journal recent: '+name,crossref,('emotion belief mental cognition human social world model intention',today,issn),'recent',None))
    # Rotate journals and relevance pages, including papers far older than two years.
    for i in range(3):
        name, issn = journal_items[(date_index*3+i)%len(journal_items)]; key='crossref:'+issn
        tasks.append(('Journal history: '+name,crossref,('emotion belief mental cognition human social world model intention',today,issn,'1900-01-01',str(cutoff-dt.timedelta(days=1)),pages.get(key,0)),'history',key))
    for year in (today.year,today.year-1,2020+(date_index%max(1,today.year-2021))):
        for venue in ('acl','findings','emnlp','naacl','tacl'):
            tasks.append((f'ACL: {year}.{venue}',get_acl,(year,venue,today,eligible),'mixed',None))
    for theme in (themes[date_index%len(themes)],themes[(date_index+1)%len(themes)]):
        key='crossref-topic:'+theme
        tasks.append(('Crossref history: '+theme,crossref,(' '.join(ARXIV_THEMES[theme]),today,None,'1900-01-01',str(cutoff-dt.timedelta(days=1)),pages.get(key,0)),'history',key))
    papers=[];ok=[];errors=[];not_available=[];fallbacks=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(fn,*args):(name,lane,key) for name,fn,args,lane,key in tasks}
        for future in as_completed(futures):
            name,lane,key=futures[future]
            try:
                result=future.result()
                if isinstance(result,tuple) and len(result)==4:
                    rows,total,backend,warning=result
                    if backend=='datacite':
                        fallbacks.append(name+': DataCite arXiv DOI metadata; '+warning)
                        name+=' via DataCite'
                        if key:key=key.replace('arxiv:','datacite:',1)
                else:rows,total=result if isinstance(result,tuple) else (result,None)
                for p in rows:
                    p['_lane']='recent' if date_floor(p['published'])>=cutoff else 'history'
                papers.extend(rows);ok.append(name)
                if key:
                    old=pages.get(key,0);step=60 if key.startswith(('arxiv:','datacite:')) else 70
                    # Crossref's relevance offset is bounded; empty pages restart a topic.
                    pages[key]=old+step if (old+step<total if total is not None else bool(rows) and old<980) else 0
                print(f'{name}: {len(rows)} candidates',flush=True)
            except Exception as ex:
                if isinstance(ex,urllib.error.HTTPError) and ex.code==404 and name.startswith('ACL: '):
                    not_available.append(name);continue
                errors.append(name+': '+str(ex)[:600]);print('Source unavailable: '+errors[-1],flush=True)
    if not ok:
        raise RuntimeError('All sources failed; preserve published library')
    unique=[];seen=set()
    for p in sorted(papers,key=lambda p:(p['status']=='published',score(p,today)),reverse=True):
        if not eligible(p,today):continue
        identities=keys(p)
        if identities&seen:
            match=next(x for x in unique if keys(x)&identities)
            match['doi_aliases']=sorted(set(match.get('doi_aliases',[])+p.get('doi_aliases',[])+[p['doi']]))
            match['url_aliases']=sorted(set(match.get('url_aliases',[])+[p['url']]))
            seen|=identities;continue
        p['group']=classify(p['venue']);p['topic']=topic(p)
        if re.search(r'cogniti\w*|human learning|human reading|hippocamp\w*',p['title'],re.I) and p['topic']=='mind':p['topic']='cognition'
        unique.append(p);seen|=identities
    return unique,{'successful_sources':sorted(ok),'unavailable_sources':sorted(errors),'fallback_sources':sorted(fallbacks),'not_published_sources':sorted(not_available),
                  'candidate_count':len(unique),'recent_candidates':sum(p['_lane']=='recent' for p in unique),
                  'historical_candidates':sum(p['_lane']=='history' for p in unique),'search_mode':'recent-and-historical',
                  '_next_state':state}
