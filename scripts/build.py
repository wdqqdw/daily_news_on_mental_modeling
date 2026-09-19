"""Render the cumulative document. Existing daily archives remain untouched."""
import html
import json
from collections import Counter
from core import ROOT,SITE,NAME,REPO,save_json
from library_core import GROUPS,TOPICS,load_library

def e(value):return html.escape(str(value),quote=True)
def icon(name):
    paths={'book':'<path d="M3 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H3z"/><path d="M21 4h-6a3 3 0 0 0-3 3v14a4 4 0 0 1 4-3h5z"/>','search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>','check':'<path d="m5 12 4 4L19 6"/>','file':'<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h6"/>','arrow':'<path d="M6 18 18 6M6 6h12v12"/>','download':'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>'}
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>'

def paper(p):
    pid=p['id'];search=' '.join(str(p.get(k,'')) for k in ('title','title_zh','venue','authors','doi','summary','method','target'))+' '+TOPICS[p['topic']]
    details=''.join(f'<div><dt>{label}</dt><dd>{e(p[key])}</dd></div>' for key,label in [('target','研究对象'),('method','核心方法'),('evidence','研究依据'),('limitation','阅读边界')])
    links=f'<a href="{e(p["url"])}" target="_blank" rel="noopener">论文原文 {icon("arrow")}</a>'
    if p.get('pdf'):links+=f'<a href="{e(p["pdf"])}" target="_blank" rel="noopener">PDF {icon("arrow")}</a>'
    return f'''<article class="paper-entry" id="{pid}" data-paper data-id="{pid}" data-topic="{p['topic']}" data-group="{p['group']}" data-venue="{e(p['venue'])}" data-date="{p['published']}" data-added="{p['added']}" data-search="{e(search)}">
<div class="paper-heading"><div class="paper-copy"><div class="paper-meta"><span class="venue">{e(p['venue'])}</span><span>{e(p['published'])}</span><span class="topic-tag">{TOPICS[p['topic']]}</span><span class="kind">{e(p.get('kind','方法研究'))}</span></div><h3><a href="{e(p['url'])}" target="_blank" rel="noopener">{e(p['title_zh'])}</a></h3><p class="english-title" lang="en">{e(p['title'])}</p></div><button class="mark-read" data-read-id="{pid}" aria-label="标记看过：{e(p['title_zh'])}" aria-pressed="false" title="标记看过" disabled>{icon('check')}<span>标记看过</span></button></div>
<p class="paper-summary">{e(p['summary'])}</p><div class="paper-bottom"><span class="authors">{e(p['authors'])}</span><div class="paper-links">{links}</div></div>
<details class="research-note"><summary><span class="chevron">›</span>研究笔记 <span class="has-note" hidden>· 有我的备注</span></summary><div class="note-content"><dl>{details}</dl><p class="source-credit">依据公开摘要整理 · <a href="{e(p['summary_source'])}" target="_blank" rel="noopener">核对来源</a>{' · DOI '+e(p['doi']) if p.get('doi') else ''}</p><label for="note-{pid}">我的备注 <span>仅保存在此浏览器，可导出备份</span></label><textarea id="note-{pid}" data-note-id="{pid}" rows="3" maxlength="12000" placeholder="记下值得借鉴的方法，或者下一次想追问的问题……"></textarea><span class="note-saved" role="status"></span></div></details></article>'''

def build():
    data=load_library();papers=data['papers'];counts=Counter(p['group'] for p in papers)
    status=json.loads((ROOT/'data/collection_status.json').read_text())
    save_json(SITE/'collection-status.json',status)
    checked=status['checked_at'][:16].replace('T',' ')
    groupnav=''.join(f'<button class="source-nav" data-group-filter="{key}"><span class="nav-number">{number}</span><span>{"NSC 正刊" if key=="main" else "NSC 系列期刊" if key=="family" else "AI 会议与期刊"}</span><b data-nav-count="{key}">{counts[key]}</b></button>' for key,(number,title,desc) in GROUPS.items())
    topicoptions=''.join(f'<option value="{key}">{label}</option>' for key,label in TOPICS.items())
    sections=''
    for key,(number,title,desc) in GROUPS.items():
        rows=''.join(paper(p) for p in sorted((p for p in papers if p['group']==key),key=lambda p:(p['published'],p['title']),reverse=True))
        sections+=f'<section class="source-section" data-section="{key}" id="section-{key}"><header class="section-heading"><span class="section-number">{number}</span><div><h2>{title} <span data-group-count="{key}">{counts[key]}</span></h2><p>{desc}</p></div></header><div class="paper-list">{rows}</div><p class="group-empty" hidden>这个分类暂时没有符合条件的论文。</p></section>'
    css=(SITE/'notebook.css').read_text();js=(SITE/'library.js').read_text()
    config=json.dumps({'updated':data['updated'],'papers':[{'id':p['id'],'title':p['title'],'title_zh':p['title_zh'],'doi':p.get('doi',''),'url':p['url'],'venue':p['venue'],'published':p['published']} for p in papers]},ensure_ascii=False).replace('<','\\u003c')
    page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="一份持续积累的心智建模文献库。按阅读状态与刊物分类，关注情感、信念、意图、人格与人的世界模型。"><meta name="theme-color" content="#f7f7f2"><title>心智建模文献库 · {NAME}</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='8' fill='%233d6156'/%3E%3Ctext x='9' y='29' font-size='29' font-family='Georgia' fill='white'%3Em%3C/text%3E%3C/svg%3E"><style>{css}</style></head><body data-library-updated="{data['updated']}" data-collection-checked="{status['checked_at']}"><a class="skip" href="#main">跳到论文列表</a>
<aside class="sidebar"><a class="brand" href="index.html"><span class="brand-icon">{icon('book')}</span><span>Mental Modeling<small>研究人的内在世界</small></span></a><p class="nav-label">我的文献</p><nav aria-label="阅读状态"><button class="state-nav active" data-state="unread" aria-pressed="true"><span class="state-symbol">◯</span>没看过<b id="unread-count">{len(papers)}</b></button><button class="state-nav" data-state="read" aria-pressed="false"><span class="state-symbol">✓</span>看过<b id="read-count">0</b></button></nav><div class="sidebar-rule"></div><p class="nav-label">来源分类</p><nav class="source-navigation" aria-label="论文来源"><button class="source-nav active" data-group-filter="all"><span class="nav-number">▤</span><span>全部来源</span><b data-nav-count="all">{len(papers)}</b></button>{groupnav}</nav><div class="sidebar-bottom"><div class="collection-label"><i></i>持续积累的研究文档</div><p>情感 · 信念 · 意图<br>人格 · 认知 · 社会世界</p><a href="archive.html">旧版推送存档 ↗</a><a href="{REPO}" target="_blank" rel="noopener">公开文献库 ↗</a></div></aside>
<div class="workspace"><header class="topbar"><div class="breadcrumb">{icon('file')}<span>文献库</span><span class="slash">/</span><strong id="crumb-state">没看过</strong></div><div class="document-tools"><button id="export-reading" title="导出阅读状态与备注">{icon('download')}<span>导出笔记</span></button><button id="import-button" class="import-label">导入</button><input id="import-reading" type="file" accept="application/json,.json" hidden></div></header>
<main id="main"><header class="document-header"><p class="eyebrow">DAILY NEWS ON MENTAL MODELING</p><h1>心智建模文献库<span class="title-dot">.</span></h1><p class="intro">理解情绪如何发生，信念如何形成，意图如何被推断。<br>从人的内在状态，读到人与人的世界。</p><div class="document-meta"><span>{len(papers)} 篇文献</span><span>6 个研究方向</span><span>收录更新于 <time>{data['updated'].replace('-','.')}</time></span></div></header>
<div class="reading-context"><span class="context-icon">{icon('book')}</span><p><strong id="view-label">没看过</strong><span id="view-help">把感兴趣的研究留在这里，读完一篇，勾选移入「看过」。</span></p><span class="context-count"><b id="view-count">{len(papers)}</b> 篇</span></div>
<div class="filterbar"><label class="searchbox">{icon('search')}<input id="search" type="search" placeholder="搜索标题、方法、作者或关键词…" aria-label="搜索当前阅读状态的论文"><kbd>/</kbd></label><label class="select-wrap mobile-source"><span class="sr-only">论文来源</span><select id="group-filter"><option value="all">全部来源</option><option value="main">NSC 正刊</option><option value="family">NSC 系列期刊</option><option value="ai">AI 会议与期刊</option></select></label><label class="select-wrap"><span class="sr-only">研究方向</span><select id="topic-filter"><option value="all">全部研究方向</option>{topicoptions}</select></label><label class="select-wrap sort"><span class="sr-only">排序</span><select id="sort"><option value="newest">发表时间 ↓</option><option value="oldest">发表时间 ↑</option><option value="added">最近收录</option></select></label></div>
<div class="results-line"><span id="results-text">显示全部 {len(papers)} 篇</span><div><button id="clear-filters" hidden>清除筛选</button><button id="expand-notes" aria-pressed="false">展开研究笔记</button></div></div>
<div id="sections">{sections}</div><section class="empty-state" id="empty-state" hidden>{icon('book')}<h2 id="empty-title">还没有看过的论文</h2><p id="empty-description">读完一篇后，点击「标记看过」，就会收进这里。</p><button id="empty-action">去没看过的文献</button></section>
<footer class="document-footer"><p>一份关于人的文献地图，慢慢读，持续积累。</p><span>阅读状态与备注存于当前浏览器 · 可导出备份</span><p class="collection-stamp">{'首版整理' if status['mode']=='curated-initial' else '最近检查'}：{checked}（北京时间） · 本次新增 {status['added_count']} 篇</p><details><summary>关于收录</summary><p>按 Nature、Science、Cell 正刊，系列期刊的具体刊名，以及人工智能会议与期刊分类。优先计算建模与方法研究，同时收录直接解释心智表征的神经与行为证据。只展示已核实的期刊或会议论文；预印本不作为正式刊物收录。摘要是阅读线索，研究边界包含编辑判断，请以原文为准。每日检索可用来源，有合格新文献时累积加入，不设每日篇数门槛。</p></details></footer></main></div><div id="notice" class="toast" role="status" aria-live="polite" hidden><span></span><button id="undo" hidden>撤销</button></div><noscript><p class="nojs">当前展示全部文献。启用 JavaScript 可使用阅读状态、搜索和备注。</p></noscript><script id="library-config" type="application/json">{config}</script><script>{js}</script></body></html>'''
    (SITE/'index.html').write_text(page)
    (SITE/'.nojekyll').touch()
    print(f'Built research document: {len(papers)} papers; '+str(dict(counts)))

if __name__=='__main__':build()
