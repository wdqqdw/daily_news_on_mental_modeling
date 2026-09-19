"""Validate generated documents, every local destination and fragment."""
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
from core import SITE,NAME
from library_core import load_library

class Document(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=set();self.papers=0;self.titles=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:
            assert a['id'] not in self.ids,'Duplicate HTML id';self.ids.add(a['id'])
        if tag=='article' and a.get('class') in ('paper-card','paper-entry'):self.papers+=1
        if tag=='title':self.titles+=1
        if tag in ('a','script','link','img'):
            value=a.get('href') or a.get('src')
            if value:self.links.append(value)

def check():
    docs={}
    for path in SITE.rglob('*.html'):
        doc=Document();text=path.read_text();doc.feed(text);docs[path.resolve()]=doc
        assert doc.titles==1 and NAME in text
        assert 'AI 公司动态' not in text
        if path==SITE/'index.html':
            library=load_library()
            assert doc.papers==len(library['papers'])
            assert {p['id'] for p in library['papers']} <= doc.ids
            assert {'section-main','section-family','section-ai','read-count','unread-count'} <= doc.ids
        elif path.name!='archive.html':assert doc.papers==3
    assert (SITE/'index.html').resolve() in docs and (SITE/'archive.html').resolve() in docs
    for path,doc in docs.items():
        for link in doc.links:
            u=urlsplit(link)
            if u.scheme:continue
            dest=(path.parent/unquote(u.path)).resolve() if u.path else path
            assert dest.is_relative_to(SITE.resolve()),'Escaped site path'
            assert dest.exists(),f'Broken local link: {link}'
            if u.fragment:assert unquote(u.fragment) in docs[dest].ids,f'Broken anchor {link}'
    print(f'Validated research library and {len(docs)-1} archive pages, all links and anchors')

if __name__=='__main__':check()
