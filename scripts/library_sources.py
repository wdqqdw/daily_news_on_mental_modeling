"""Primary metadata discovery for the publication-grouped research library."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import re
import threading
import time
import urllib.error
import urllib.parse
from core import date_floor, keys
from library_core import JOURNALS, classify
from sources import fetch, clean, get_acl, BAD, TARGET, off_scope_reason, topic, score

HUMAN = re.compile(r'\b(human|people|person|participants?|cogniti\w*|mental\w*|emoti\w*|empath\w*|belief\w*|intent\w*|social|hippocamp\w*|brain|concept\w* learning)\b', re.I)
SUBJECT = re.compile(TARGET.pattern + r'|cognitive map|relational memory|human learning|human reading|social navigation|hippocampus|hippocampal', re.I)
CROSSREF_LOCK = threading.Lock()

def eligible(p, today):
    abstract = p.get('_abstract', '')
    try:
        age = (today - date_floor(p['published'])).days
    except (ValueError, KeyError):
        return False
    return (p.get('status') == 'published' and classify(p['venue']) is not None
            and 0 <= age <= 730 and not BAD.search(p['title']) and not off_scope_reason(p)
            and len(abstract.split()) >= 55 and bool(SUBJECT.search(p['title']))
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

def crossref(query, today, issn=None):
    params = {'query': query, 'filter': f'from-pub-date:{today-dt.timedelta(days=730)},until-pub-date:{today}',
              'rows': 70, 'select': 'DOI,title,author,container-title,published-online,published-print,published,issued,type,is-referenced-by-count,abstract,update-to'}
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
    return crossref_rows(data['message']['items'], today)

def collect(today):
    tasks = []
    for name, issn in JOURNALS.items():
        tasks.append(('Journal: ' + name, crossref, ('emotion belief mental cognition human social world model intention', today, issn)))
    for query in ('theory of mind belief intention inference', 'emotion empathy personality psychological model', 'human cognitive social world model'):
        tasks.append(('Crossref: ' + query, crossref, (query, today)))
    for year in (today.year, today.year - 1):
        for venue in ('acl', 'findings', 'emnlp', 'naacl', 'tacl'):
            tasks.append((f'ACL: {year}.{venue}', get_acl, (year, venue, today)))
    papers = []; ok = []; errors = []; not_available = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn, *args): name for name, fn, args in tasks}
        for future in as_completed(futures):
            name = futures[future]
            try:
                rows = future.result(); papers.extend(rows); ok.append(name)
                print(f'{name}: {len(rows)} candidates', flush=True)
            except Exception as ex:
                if isinstance(ex, urllib.error.HTTPError) and ex.code == 404 and name.startswith('ACL: '):
                    not_available.append(name)
                    continue
                errors.append(name + ': ' + str(ex)[:160])
                print('Source unavailable: ' + errors[-1], flush=True)
    if not ok:
        raise RuntimeError('All sources failed; preserve published library')
    unique = []; seen = set()
    for p in sorted(papers, key=lambda p: score(p, today), reverse=True):
        if not eligible(p, today):
            continue
        identities = keys(p)
        if identities & seen:
            continue
        p['group'] = classify(p['venue']); p['topic'] = topic(p)
        if re.search(r'cogniti\w*|human learning|human reading|hippocamp\w*', p['title'], re.I) and p['topic'] == 'mind':
            p['topic'] = 'cognition'
        unique.append(p); seen |= identities
    return unique, {'successful_sources': sorted(ok), 'unavailable_sources': sorted(errors), 'not_published_sources': sorted(not_available), 'candidate_count': len(unique)}
