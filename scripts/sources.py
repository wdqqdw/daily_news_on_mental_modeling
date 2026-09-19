"""Public, primary scholarly sources; abstracts stay in the ignored cache."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import datetime as dt
import html
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from core import ROOT,date_floor,keys

AGENT='DailyMentalModeling/1.0 (+https://github.com/wdqqdw/daily_news_on_mental_modeling)'
BAD=re.compile(r'\b(survey|systematic review|scoping review|bibliometric|editorial|corrigendum|retraction|technical report|system card|model card|position paper)\b',re.I)
TARGET=re.compile(r'\b(theory.of.mind|mental (?:states?|model\w*|health)|mentaliz\w*|emoti\w*|affective|empath\w*|appraisal|belief\w*|intentions?|intent inference|intent recognition|goal inference|personality|psycholog\w*|social (?:cogni\w*|world|simulat\w*)|human (?:behavio\w*|cogni\w*|decision\w*|preferen\w*))\b',re.I)
CONTRIBUTION=re.compile(r'\b(?:we(?:\s+\w+){0,2}|this (?:paper|work|study|article))\s+(?:propos\w*|introduc\w*|develop\w*|present\w*|design\w*)\b',re.I)
METHOD_OBJECT=re.compile(r'\b(framework|algorithm|architecture|model|method|approach|agents?|system|inference procedure|training strategy)\b',re.I)
EVALUATION_OBJECT=re.compile(r'\b(benchmarks?|datasets?|corpus|evaluation (?:protocol|framework)|assessment (?:protocol|framework))\b',re.I)
CONTENT_TASK=re.compile(r'\b(cyberbullying|hate speech|toxicity|toxic content|fake news|misinformation|spam)\b',re.I)
EXPLICIT_MIND=re.compile(r'\b(theory.of.mind|mental states?|belief\w*|intent\w*|personality|cognitive appraisal|emotion[ -](?:cause|shift|dynamics|reasoning))\b',re.I)
AI=re.compile(r'\b(language models?|LLMs?|neural|computational|bayesian|learning|transformer|artificial intelligence|agent)\b',re.I)
TOPIC_PATTERNS={
 'emotion':r'emoti\w*|affectiv\w*|empath\w*|appraisal',
 'mind':r'theory.of.mind|mentaliz\w*|belief\w*|epistemic',
 'intent':r'intention\w*|intent inference|intent recognition|goal inference|inverse planning',
 'world':r'social world|social simulat\w*|human behavio\w*|world model',
 'person':r'personality|psycholog\w*|mental health|mental states?|cognitive model'
}

def clean(text):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',text or ''))).strip()
def xt(el):return '' if el is None else clean(''.join(el.itertext()))

def fetch(url):
    headers={'User-Agent':AGENT}
    if url.startswith('https://api.github.com/') and os.getenv('GITHUB_TOKEN'):
        headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    if '/contents/' in url:headers['Accept']='application/vnd.github.raw+json'
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=35) as r:
                return r.read(25_000_000).decode('utf-8','replace')
        except urllib.error.HTTPError as ex:
            if ex.code in (400,401,403,404) or attempt==2:raise
        except (OSError,TimeoutError,urllib.error.URLError):
            if attempt==2:raise
        time.sleep(2**attempt)

def has_method_contribution(abstract):
    """A benchmark's comparison to an existing model is not a new modeling method."""
    for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',abstract):
        for match in CONTRIBUTION.finditer(sentence):
            claim=sentence[match.end():match.end()+320]
            if METHOD_OBJECT.search(claim) and not EVALUATION_OBJECT.search(claim):
                return True
    return False

def off_scope_reason(p):
    title=p.get('title','')
    if re.search(r'\b(?:KV[ -]cache|cache compression|cache eviction)\b',title,re.I):
        return '缓存优化不是对人的意图或心智进行建模。'
    # Possessive wording and explicit stability studies target the model's own
    # beliefs, unlike LLM-based inference of another person's mental states.
    if (re.search(r'\bLLMs?[’\']\s*(?:stated\s+)?belief',title,re.I)
        or re.search(r'\bLLMs?\s+belief\s+resistance\b',title,re.I)
        or re.search(r'\bepistemic resilience of (?:LLMs?|language models?)\b',title,re.I)):
        return '研究语言模型自身信念的稳定性，不是推断或模拟人的心智。'
    return ''

def eligible(p,today):
    title=p.get('title','');abstract=p.get('_abstract','');text=title+' '+abstract
    if off_scope_reason(p):return False
    # An emotion-aware content filter is not a model of someone's mental state.
    # Keep content-related research only when its stated subject explicitly
    # includes mental-state, intention, belief, or appraisal modeling.
    if CONTENT_TASK.search(title) and not EXPLICIT_MIND.search(title):return False
    try:age=(today-date_floor(p['published'])).days
    except (ValueError,KeyError):return False
    return (0<=age<=730 and len(abstract.split())>=55 and not BAD.search(title)
            and bool(TARGET.search(title)) and has_method_contribution(abstract) and bool(AI.search(text)))

def topic(p):
    for key in ('world','intent','person','emotion','mind'):
        if re.search(TOPIC_PATTERNS[key],p['title'],re.I):return key
    text=p['title']+' '+p['_abstract'][:500]
    # Explicit world models and intention inference take priority over incidental emotion/belief wording.
    for key in ('world','intent','emotion','mind','person'):
        if re.search(TOPIC_PATTERNS[key],text,re.I):return key
    return 'mind'

def score(p,today):
    age=max((today-date_floor(p['published'])).days,0)
    topical=len({m.group().lower() for m in TARGET.finditer(p['title'])})
    return 8*math.exp(-age/210)+min(topical,3)+(.7 if p['status']=='published' else 0)+min(math.log1p(p.get('citations',0)),2)/2

def acl_xml(content,today):
    root=ET.fromstring(content);out=[]
    months={name:i for i,name in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
    for vol in root.findall('volume'):
        meta=vol.find('meta')
        if meta is None:continue
        year=xt(meta.find('year'));month=months.get(xt(meta.find('month')))
        if not re.fullmatch(r'\d{4}',year):continue
        published=year+(f'-{month:02}' if month else '')
        # Volume ids distinguish ACL/EMNLP Findings without guessing paper URLs.
        coll=root.get('id');volume=vol.get('id')
        venue=(('Findings of '+volume.upper()) if coll.endswith('.findings') else coll.split('.',1)[1].upper())+' '+year
        for paper in vol.findall('paper'):
            identity=f'{coll}-{volume}.{paper.get("id")}'
            author=paper.find('author');authors=(xt(author.find('first'))+' '+xt(author.find('last'))) if author is not None else 'Authors in paper'
            if len(paper.findall('author'))>1:authors+=' et al.'
            url=f'https://aclanthology.org/{identity}/'
            p={'title':xt(paper.find('title')),'_abstract':xt(paper.find('abstract')),'doi':xt(paper.find('doi')),'url':url,'pdf':f'https://aclanthology.org/{identity}.pdf','venue':venue,'published':published,'authors':authors,'status':'published','metadata_source':'ACL Anthology','summary_source':url}
            if paper.find('retraction') is not None or paper.find('withdrawal') is not None:continue
            if eligible(p,today):out.append(p)
    return out

def get_acl(year,venue,today):
    url=f'https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/{year}.{venue}.xml'
    try:content=fetch(url)
    except (OSError,urllib.error.URLError):
        content=fetch(f'https://api.github.com/repos/acl-org/acl-anthology/contents/data/xml/{year}.{venue}.xml')
    return acl_xml(content,today)

def get_crossref(query,today):
    params={'query.title':query,'filter':f'from-pub-date:{today-dt.timedelta(days=730)},until-pub-date:{today}','rows':80,
     'select':'DOI,title,author,container-title,publisher,published-online,published-print,published,issued,type,is-referenced-by-count,abstract,update-to'}
    data=json.loads(fetch('https://api.crossref.org/works?'+urllib.parse.urlencode(params)))['message']['items'];out=[]
    for x in data:
        if x.get('type') not in ('journal-article','proceedings-article') or not x.get('DOI'):continue
        if any(u.get('type') in ('retraction','withdrawal') for u in x.get('update-to',[])):continue
        dates=[]
        for key in ('published-online','published-print','published','issued'):
            parts=x.get(key,{}).get('date-parts',[[]])[0]
            if 1<=len(parts)<=3:
                v='-'.join(str(n) if i==0 else f'{n:02}' for i,n in enumerate(parts))
                try:date_floor(v);dates.append(v)
                except ValueError:pass
        if not dates:continue
        published=min(dates,key=date_floor)
        venue=clean(' '.join(x.get('container-title',[])))
        if not venue:continue
        au=x.get('author',[]);a=au[0] if au else {}
        doi=x['DOI'].lower();url='https://doi.org/'+doi
        p={'title':clean(' '.join(x.get('title',[]))),'_abstract':clean(x.get('abstract','')),'doi':doi,'url':url,'venue':venue,'published':published,'authors':a.get('given','')+' '+a.get('family',a.get('name','Authors in paper'))+(' et al.' if len(au)>1 else ''),'status':'published','citations':x.get('is-referenced-by-count',0),'metadata_source':'Crossref','summary_source':'https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='')}
        if eligible(p,today):out.append(p)
    return out

def arxiv_xml(content,today):
    root=ET.fromstring(content);out=[];ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}
    for entry in root.findall('a:entry',ns):
        identifier=xt(entry.find('a:id',ns));m=re.search(r'(\d{4}\.\d{4,5})(?:v\d+)?$',identifier)
        if not m:continue
        aid=m[1];url='https://arxiv.org/abs/'+aid
        authors=[xt(a.find('a:name',ns)) for a in entry.findall('a:author',ns)]
        paper_doi=xt(entry.find('x:doi',ns))
        p={'title':xt(entry.find('a:title',ns)),'_abstract':xt(entry.find('a:summary',ns)),'published':xt(entry.find('a:published',ns))[:10],'url':url,'pdf':'https://arxiv.org/pdf/'+aid,'doi':'10.48550/arXiv.'+aid,'doi_aliases':[paper_doi] if paper_doi else [],'authors':authors[0]+(' et al.' if len(authors)>1 else '') if authors else 'Authors in paper','venue':'arXiv','status':'preprint','metadata_source':'arXiv','summary_source':url}
        # An author-supplied journal-ref alone never upgrades review status.
        if eligible(p,today):out.append(p)
    return out

def get_arxiv(today):
    terms=['theory of mind','emotional reasoning','emotion recognition','social world model','intention inference','mental state','personality modeling','human behavior modeling','cognitive appraisal','mental health']
    query='('+ ' OR '.join('ti:"'+q+'"' for q in terms)+') AND submittedDate:['+(today-dt.timedelta(days=730)).strftime('%Y%m%d')+'0000 TO '+today.strftime('%Y%m%d')+'2359]'
    url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':query,'start':0,'max_results':160,'sortBy':'submittedDate','sortOrder':'descending'})
    return arxiv_xml(fetch(url),today)

def collect(today,include_preprints=True):
    tasks=[]
    for year in (today.year,today.year-1):
        for venue in ('acl','findings','emnlp','naacl','eacl','tacl','lrec','coling','wassa'):
            tasks.append((f'ACL {year}.{venue}',get_acl,(year,venue,today)))
    for query in ('theory of mind language model','emotional intelligence appraisal model','human intention inference','social world model','personality psychological state language model','computational cognitive model human'):
        tasks.append(('Crossref '+query,get_crossref,(query,today)))
    if include_preprints:tasks.append(('arXiv',get_arxiv,(today,)))
    papers=[];ok=[];errors=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        pending={pool.submit(fn,*args):name for name,fn,args in tasks}
        for future in as_completed(pending):
            name=pending[future]
            try:
                rows=future.result();papers.extend(rows);ok.append(name)
                print(f'Source {name}: {len(rows)} topical candidates',flush=True)
            except Exception as ex:
                errors.append(name+': '+str(ex)[:160])
                print('Source unavailable: '+errors[-1],flush=True)
    if not ok or not papers:raise RuntimeError('No usable sources; retain previous edition')
    # Prefer formal publications when the same title/DOI appears on several sources.
    papers.sort(key=lambda p:(p['status']=='published',score(p,today)),reverse=True)
    seen=set();unique=[]
    for p in papers:
        kk=keys(p)
        if not kk&seen:
            p['topic']=topic(p);unique.append(p);seen |= kk
        else:
            existing=next((x for x in unique if keys(x)&kk),None)
            if existing:
                existing['doi_aliases']=list(set(existing.get('doi_aliases',[])+p.get('doi_aliases',[])+([p['doi']] if p.get('doi') else [])))
                existing['url_aliases']=list(set(existing.get('url_aliases',[])+[p['url']]))
                seen |= kk
    return unique,{'successful_sources':ok,'unavailable_sources':errors,'candidate_count':len(unique)}
