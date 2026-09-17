"""Shared publication contract and permanent cross-source deduplication."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'issues'
SITE = ROOT / 'site'
NAME = 'Daily News on Mental Modeling'
REPO = 'https://github.com/wdqqdw/daily_news_on_mental_modeling'
TOPICS = {'emotion':'情感智能', 'mind':'心智与信念', 'intent':'意图与目标', 'world':'人的世界模型', 'person':'人格与心理状态'}
FIELDS = ('title_zh','summary','target','method','evidence','limitation')

def title_key(title):
    return ''.join(c for c in unicodedata.normalize('NFKC', title).casefold() if c.isalnum())

def doi_key(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', unquote(value).strip().casefold())

def keys(p):
    result = {'title:'+title_key(p['title'])}
    if p.get('title_zh'): result.add('title:'+title_key(p['title_zh']))
    for doi in [p.get('doi',''), *p.get('doi_aliases',[])]:
        if doi: result.add('doi:'+doi_key(doi))
    for url in [p['url'], *p.get('url_aliases',[])]:
        parts=urlsplit(url)
        result.add('url:'+urlunsplit(('https',parts.netloc.lower(),parts.path.rstrip('/'),'','')))
        arxiv = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?',url)
        if arxiv: result.add('arxiv:'+arxiv[1])
    return result

def uid(p):
    identity = doi_key(p['doi']) if p.get('doi') else p['url']
    return 'paper-'+hashlib.sha256(identity.encode()).hexdigest()[:16]

def date_floor(value):
    # Padding is used for sorting only. Display always preserves source precision.
    if not re.fullmatch(r'\d{4}(?:-\d{2})?(?:-\d{2})?',value): raise ValueError('Invalid publication date')
    return dt.date.fromisoformat(value + {4:'-01-01',7:'-01',10:''}[len(value)])

def safe_url(value):
    p=urlsplit(value)
    if p.scheme!='https' or not p.hostname or p.username: raise ValueError('Invalid source URL')
    return value

def validate(issue):
    today=dt.date.fromisoformat(issue['date'])
    stamp=dt.datetime.fromisoformat(issue['generated_at'])
    if stamp.tzinfo is None or stamp.date()!=today: raise ValueError('Edition timestamp mismatch')
    if len(issue['papers'])!=3: raise ValueError('Exactly three papers required')
    used=set()
    for p in issue['papers']:
        if p['topic'] not in TOPICS: raise ValueError('Unknown topic')
        if p['status'] not in ('published','preprint'): raise ValueError('Unknown publication status')
        if date_floor(p['published'])>today: raise ValueError('Future publication')
        for f in ('title','venue','authors',*FIELDS):
            if not isinstance(p.get(f),str) or not p[f].strip(): raise ValueError('Missing '+f)
        for f in FIELDS:
            if not re.search(r'[\u4e00-\u9fff]',p[f]): raise ValueError('Missing Chinese explanation: '+f)
        safe_url(p['url']);safe_url(p['summary_source'])
        for f in ('pdf','code','status_source'):
            if p.get(f):safe_url(p[f])
        current=keys(p)
        if used & current: raise ValueError('Duplicate paper')
        used |= current

def history():
    file=ROOT/'data/history.json'
    records=json.loads(file.read_text()) if file.exists() else []
    used={k for r in records for k in r['keys']}
    for file in sorted(DATA.glob('*.json')):
        issue=json.loads(file.read_text())
        for p in issue['papers']:
            kk=keys(p)
            matching=next((r for r in records if set(r['keys'])&kk),None)
            if matching:matching['keys']=sorted(set(matching['keys'])|kk)
            else:records.append({'first_pushed':issue['date'],'title':p['title'],'url':p['url'],'keys':sorted(kk)})
            used |= kk
    return records

def assert_unseen(issue, records):
    used={k for r in records for k in r['keys']}
    for p in issue['papers']:
        kk=keys(p)
        if kk & used: raise ValueError('Already published: '+p['title'])
        used |= kk

def save_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    tmp.replace(path)
