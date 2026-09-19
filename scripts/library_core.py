"""Publication taxonomy and stable identities for the cumulative reading document."""
import datetime as dt
import json
import re
from core import ROOT, SITE, keys, uid, safe_url, date_floor, FIELDS

LIBRARY=ROOT/'data/library.json'
GROUPS={
 'main':('01','Nature / Science / Cell 正刊','三本正刊中的心智、认知与行为研究。'),
 'family':('02','Nature / Science / Cell 系列期刊','按具体刊名整理，连接计算模型与人的行为证据。'),
 'ai':('03','人工智能会议与期刊','将会议和期刊放在一起，关注可实现的建模方法。'),
 'arxiv':('04','arXiv / 预印本','收录 arXiv 版本；未独立核验的期刊或会议发表状态不作认定。'),
}
GROUP_LABELS={'main':'NSC 正刊','family':'NSC 系列期刊','ai':'AI 会议与期刊','arxiv':'arXiv / 预印本'}
TOPICS={'emotion':'情感与共情','mind':'心智与信念','intent':'意图与目标','world':'人的世界模型','person':'人格与心理状态','cognition':'认知与决策'}
JOURNALS={
 'Nature':'0028-0836','Science':'0036-8075','Cell':'0092-8674',
 'Nature Human Behaviour':'2397-3374','Nature Machine Intelligence':'2522-5839',
 'Nature Neuroscience':'1097-6256','Nature Communications':'2041-1723',
 'Communications Psychology':'2731-9121','Scientific Reports':'2045-2322',
 'Science Advances':'2375-2548','Science Robotics':'2470-9476',
 'Neuron':'0896-6273','Current Biology':'0960-9822','Cell Reports':'2211-1247',
 'Trends in Cognitive Sciences':'1364-6613',
}
AI_JOURNALS={'Journal of Artificial Intelligence Research','Journal of Machine Learning Research','Artificial Intelligence','IEEE Transactions on Affective Computing','IEEE Transactions on Pattern Analysis and Machine Intelligence','Neural Networks','Neurocomputing','Knowledge-Based Systems','Transactions of the Association for Computational Linguistics','TACL'}

def classify(venue):
    name=re.sub(r'\s+',' ',venue).strip()
    if name=='arXiv':return 'arxiv'
    if name in ('Nature','Science','Cell'):return 'main'
    if name in JOURNALS:return 'family'
    if name in AI_JOURNALS or re.fullmatch(r'(?:Findings of )?(?:ACL|EMNLP|NAACL|EACL|COLING|TACL|ICML|ICLR|NeurIPS|AAAI|IJCAI|AISTATS|CVPR|ICCV|ECCV|AAMAS|CHI|UIST|HRI|CogSci)(?: \d{4})?',name):return 'ai'
    return None

def validate_library(data):
    assert data['version']==2
    dt.date.fromisoformat(data['updated'])
    seen=set()
    for p in data['papers']:
        assert p['group'] in GROUPS and classify(p['venue'])==p['group'], 'Incorrect publication group: '+p['venue']
        assert p['topic'] in TOPICS
        assert p['status']==('preprint' if p['group']=='arxiv' else 'published'), 'Publication status and source group disagree'
        assert date_floor(p['published'])<=dt.date.fromisoformat(data['updated'])
        dt.date.fromisoformat(p['added'])
        for k in ('title','venue','authors',*FIELDS):assert isinstance(p.get(k),str) and p[k].strip(), 'Missing '+k
        for k in ('url','summary_source'):safe_url(p[k])
        for k in ('pdf','code','status_source'):
            if p.get(k):safe_url(p[k])
        for k in FIELDS:assert re.search(r'[\u4e00-\u9fff]',p[k]),'Missing Chinese explanation: '+k
        assert not keys(p)&seen, 'Duplicate paper: '+p['title']
        seen|=keys(p)
        assert p['id']==uid(p),'Unstable reading identity'
    assert data['papers'],'Empty library'

def load_library():
    data=json.loads(LIBRARY.read_text());validate_library(data);return data
