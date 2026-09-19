"""Build self-contained daily snapshots and a searchable reading archive."""
import argparse
import datetime as dt
import html
import json
from core import ROOT,DATA,SITE,NAME,REPO,TOPICS,validate,uid,history,assert_unseen,keys,save_json

def e(v): return html.escape(str(v),quote=True)

def button(p):
    return f'<button class="read-toggle" type="button" data-read-id="{uid(p)}" data-read-title="{e(p["title_zh"])}" aria-pressed="false" disabled><span class="read-check" aria-hidden="true">✓</span><span class="read-label">标记已了解</span></button>'

def frame(title,body,archive=False,prefix=''):
    css=(SITE/'style.css').read_text()
    js=(SITE/'reading.js').read_text()
    favicon="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'%3E%3Crect width='40' height='40' rx='9' fill='%231b365d'/%3E%3Cpath d='M9 29V11l11 12 11-12v18' fill='none' stroke='white' stroke-width='3'/%3E%3C/svg%3E"
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="每日三篇人类心智建模论文，聚焦情感智能、心智理论、意图推断、心理状态与人的世界模型。"><meta name="theme-color" content="#1b365d"><title>{e(title)} · {NAME}</title><link rel="icon" href="{favicon}"><style>{css}</style></head><body><a class="skip" href="#main">跳到正文</a><div class="wrap"><header class="topbar"><a href="{prefix}index.html" class="brand"><span class="mark" aria-hidden="true">M</span><span>MENTAL MODELING<span class="brand-small">研究人的智能</span></span></a><nav aria-label="主导航"><a href="{prefix}index.html" {'aria-current="page"' if not archive else ''}>今日论文</a><a href="{prefix}archive.html" {'aria-current="page"' if archive else ''}><span aria-hidden="true">▤</span> 历史推送</a></nav></header>{body}<footer><span>{NAME}</span><span>北京时间 · <a href="{REPO}" target="_blank" rel="noopener">GitHub</a></span></footer><p id="reading-status" role="status" aria-live="polite"></p><noscript><p class="notice">启用 JavaScript 后可使用阅读标记和历史搜索，论文原文及归档仍可直接访问。</p></noscript></div><script>{js}</script></body></html>'''

def badge(p):
    return '<span class="status preprint">预印本 · 未经同行评审</span>' if p['status']=='preprint' else '<span class="status">正式发表 / 录用</span>'

def card(p,n):
    links=f'<a class="primary-link" href="{e(p["url"])}" target="_blank" rel="noopener">阅读论文 ↗</a>'
    for f,label in [('pdf','PDF'),('code','代码')]:
        if p.get(f):links+=f'<a href="{e(p[f])}" target="_blank" rel="noopener">{label} ↗</a>'
    return f'''<article class="paper-card" id="{uid(p)}" data-item-id="{uid(p)}"><div class="paper-top"><span class="topic"><span class="paper-number">{n:02}</span>{TOPICS[p['topic']]}</span>{badge(p)}</div><h2>{e(p['title_zh'])}</h2><p class="english-title" lang="en">{e(p['title'])}</p><div class="source-row"><b>{e(p['venue'])}</b><span>·</span><time datetime="{e(p['published'])}">{e(p['published'])}</time><span>·</span><span>{e(p['authors'])}</span></div><p class="summary">{e(p['summary'])}</p><div class="method-grid"><section><h3>建模对象 <span>WHAT</span></h3><p>{e(p['target'])}</p></section><section><h3>核心方法 <span>HOW</span></h3><p>{e(p['method'])}</p></section></div><details class="evidence"><summary>实验依据与研究边界</summary><div><h3>实验依据</h3><p>{e(p['evidence'])}</p><h3>研究边界</h3><p>{e(p['limitation'])}</p><p class="source-note">{e(p.get('summary_method','依据公开摘要整理'))} · <a href="{e(p['summary_source'])}" target="_blank" rel="noopener">核对来源 ↗</a>{f' · DOI: {e(p["doi"])}' if p.get('doi') else ''}</p></div></details><div class="paper-footer">{button(p)}<div class="paper-links">{links}</div></div></article>'''

def issue_page(issue,number,historical=False):
    validate(issue)
    prefix='../' if historical else ''
    warning=f'<p class="notice">正在阅读 {issue["date"]} 的历史快照。<a href="../index.html">返回最新推送</a></p>' if historical else f'<p id="stale-notice" class="notice" data-edition="{issue["date"]}" hidden></p>'
    contents=''.join(f'<a href="#{uid(p)}"><span>{n:02}</span><div>{TOPICS[p["topic"]]}<small>{e(p["title_zh"])}</small></div></a>' for n,p in enumerate(issue['papers'],1))
    scope=''.join(f'<li><span>{n:02}</span>{v}</li>' for n,v in enumerate(TOPICS.values(),1))
    cards=''.join(card(p,n) for n,p in enumerate(issue['papers'],1))
    body=f'''<main id="main"><section class="masthead"><div class="edition-label">RESEARCH DIGEST <span>VOL. {number:03}</span></div><h1>Daily News on<br><em>Mental Modeling</em></h1><div class="masthead-bottom"><p>建模人的情绪、信念、意图与内在世界。</p><div class="edition-date"><strong>{issue['date'].replace('-',' / ')}</strong><span>每日 09:00 · 北京时间</span></div></div></section><div class="section-bar"><span>本期论文 <b>03</b></span><span>方法 · 表征 · 证据</span></div>{warning}<div class="research-layout"><div class="papers">{cards}</div><aside><section class="aside-block"><h2>本期阅读 <span>IN THIS ISSUE</span></h2><div class="contents">{contents}</div></section><section class="aside-block scope"><h2>关注方向 <span>RESEARCH SCOPE</span></h2><ul>{scope}</ul><p>关注对人的内在状态进行表征、推断、预测与模拟的计算方法。</p></section><details class="policy"><summary>论文筛选与更新规则</summary><p>每天精选 3 篇，以主题与方法贡献为先，优先近期论文，适量补充较早的方法研究；原始发表日期如实显示。涵盖期刊、会议及明确标注的研究预印本。</p><p>排除公司新闻、产品发布、通用技术报告、纯物理世界模型及仅做测评的论文。自动筛选和解读依据公开摘要，不能代替阅读全文。</p><p>历史内容永久去重；候选不足时保留上一期。09:00 为计划触发时间，实际上线可能受排队及内容核验影响。</p><p>本期生成于 {e(issue['generated_at'][11:16])}，北京时间。阅读标记仅保存在当前浏览器。</p></details><a class="archive-cta" href="{prefix}archive.html"><span aria-hidden="true">▤</span><div>历史推送<small>按日期回看 · 已了解 / 未了解</small></div><span>↗</span></a></aside></div></main>'''
    return frame(issue['date']+' 论文精选',body,historical,prefix)

def entry(p,date):
    search=' '.join(str(p.get(k,'')) for k in ('title','title_zh','summary','target','method','venue','authors','doi','published'))+' '+date+' '+TOPICS[p['topic']]
    return f'''<article class="library-entry" data-library-entry data-item-id="{uid(p)}" data-search="{e(search)}"><div class="library-meta">{TOPICS[p['topic']]} · {e(p['venue'])}</div><h3><a href="{e(p['url'])}" target="_blank" rel="noopener">{e(p['title_zh'])} ↗</a></h3><p class="library-summary">{e(p['summary'])}</p><div class="library-date">发表 {e(p['published'])} · 推送 {date}</div><div class="library-footer">{button(p)}<a href="archive/{date}.html#{uid(p)}">当期解读 ↗</a></div></article>'''

def build(rebuild=False):
    issues=[json.loads(f.read_text()) for f in sorted(DATA.glob('*.json'))]
    if not issues:raise ValueError('No issues')
    records=[]
    for issue in issues:
        validate(issue);assert_unseen(issue,records)
        records += [{'keys':list(keys(p))} for p in issue['papers']]
    SITE.mkdir(exist_ok=True);(SITE/'archive').mkdir(exist_ok=True)
    for n,issue in enumerate(issues,1):
        path=SITE/'archive'/f'{issue["date"]}.html'
        if rebuild or not path.exists():path.write_text(issue_page(issue,n,True))
    (SITE/'index.html').write_text(issue_page(issues[-1],len(issues)))
    entries=''.join(entry(p,i['date']) for i in reversed(issues) for p in i['papers'])
    cols=''
    for state,label in [('read','已了解'),('unread','未了解')]:
        cols+=f'''<section class="reading-column"><div class="reading-heading"><h2>{label} <span id="{state}-count">0</span></h2></div><label for="{state}-search">搜索{label}论文</label><input type="search" id="{state}-search" data-reading-search placeholder="标题、方法、作者、期刊或日期" aria-controls="{state}-list"><div id="{state}-list">{entries if state=='unread' else ''}</div><p class="reading-empty" id="{state}-empty">暂无内容</p></section>'''
    rows=''.join(f'<a class="archive-row" href="archive/{i["date"]}.html"><span aria-hidden="true">▤</span><strong>{i["date"]}</strong><span>第 {n:03} 期 · 3 篇论文</span><span>↗</span></a>' for n,i in reversed(list(enumerate(issues,1))))
    body=f'''<main id="main"><div class="archive-head"><div class="edition-label">THE READING ARCHIVE</div><h1>历史推送</h1><p>共 {len(issues)} 期 · {len(issues)*3} 篇论文。阅读标记保存在当前浏览器，不同设备暂不互通。</p></div><div class="reading-grid">{cols}</div><section class="date-archive"><h2>按日期回看 <span class="muted">独立 HTML 快照</span></h2>{rows}</section></main>'''
    (SITE/'archive.html').write_text(frame('历史推送',body,True))
    (SITE/'.nojekyll').touch();save_json(ROOT/'data/history.json',history())
    print(f'Built {len(issues)} issues; latest {issues[-1]["date"]}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rebuild-archive',action='store_true');build(p.parse_args().rebuild_archive)
