"""One immutable, non-repeating issue per Beijing date. Failure leaves the site intact."""
import argparse
import datetime as dt
import json
from pathlib import Path
import urllib.error
from zoneinfo import ZoneInfo
from core import ROOT,DATA,history,keys,assert_unseen,validate,save_json
from sources import collect,score
from summarize import local_model,assess,summarize,MODEL_REPO
from build_digest import build

def ranked_candidates(pool,seen,today):
    remaining=[p for p in pool if not keys(p)&seen]
    # Greedy topic rotation avoids using all review attempts on one subject.
    out=[];used=set()
    while remaining:
        if len(used)>=5:used.clear()
        diverse=[p for p in remaining if p['topic'] not in used]
        p=max(diverse or remaining,key=lambda p:(score(p,today),p['title']))
        remaining.remove(p);out.append(p);used.add(p['topic'])
    return out

def make_briefs(base,candidates,cache,max_briefs=6):
    """An invalid candidate must not discard already verified briefs."""
    finished=[];audit=[];used_topics=set();deferred=[];attempts=0
    save_json(cache/'preview.json',finished)
    save_json(cache/'selection-review.json',audit)

    def finish(p,entry):
        nonlocal attempts
        attempts+=1
        try:
            brief=summarize(base,p)
        except (ValueError,OSError,urllib.error.URLError) as ex:
            entry.update(brief_status='rejected',brief_error=str(ex)[:500])
            save_json(cache/'selection-review.json',audit)
            print('Skip invalid brief: '+p['title']+'; '+str(ex),flush=True)
            return
        paper={**p,**brief,'summary_method':'AI 根据公开摘要整理并复核；研究边界包含证据范围判断','summary_model':MODEL_REPO}
        paper.pop('_abstract',None);paper.pop('citations',None)
        finished.append(paper);used_topics.add(paper['topic'])
        entry['brief_status']='ready'
        save_json(cache/'preview.json',finished)
        save_json(cache/'selection-review.json',audit)
        print('Chinese method brief ready: '+paper['title_zh'],flush=True)

    for candidate in candidates[:24]:
        if len(finished)==3 or attempts>=max_briefs:break
        p=dict(candidate)
        try:result=assess(base,p)
        except (ValueError,OSError,urllib.error.URLError) as ex:
            audit.append({'title':p['title'],'accept':False,'review_error':str(ex)[:500]})
            save_json(cache/'selection-review.json',audit)
            continue
        entry={'title':p['title'],**result};audit.append(entry)
        save_json(cache/'selection-review.json',audit)
        print('Topic review: '+str(result['accept'])+' '+p['title'],flush=True)
        if not result['accept']:continue
        p['topic']=result['topic'];p['selection_reason']=result['reason']
        if p['topic'] in used_topics:deferred.append((p,entry));continue
        finish(p,entry)
    for p,entry in deferred:
        if len(finished)==3 or attempts>=max_briefs:break
        finish(p,entry)
    if len(finished)!=3:
        raise RuntimeError(f'Only {len(finished)} verified unseen briefs after {attempts} attempts; keep previous issue')
    return finished

def run(dry_run=False,output=None,discover_only=False):
    now=dt.datetime.now(ZoneInfo('Asia/Shanghai'));today=now.date();path=DATA/f'{today}.json'
    if path.exists() and not dry_run and not discover_only:
        print('Existing edition preserved: '+str(today));build();return
    config=json.loads((ROOT/'data/policy.json').read_text())
    records=history();seen={k for r in records for k in r['keys']}
    pool,report=collect(today,config['include_preprints'])
    candidates=ranked_candidates(pool,seen,today)
    cache=ROOT/'.cache';cache.mkdir(exist_ok=True)
    # Source abstracts are temporary inputs, never public repository content.
    save_json(cache/'candidates.json',candidates)
    report['unseen_candidates']=len(candidates);save_json(cache/'source-report.json',report)
    print(f'{len(candidates)} unseen candidates',flush=True)
    if discover_only:return
    with local_model() as base:
        selected=make_briefs(base,candidates,cache)
    completed=dt.datetime.now(ZoneInfo('Asia/Shanghai'))
    if completed.date()!=today:raise RuntimeError('Date changed during generation; retry for the new day')
    issue={'date':str(today),'generated_at':completed.isoformat(timespec='seconds'),'papers':selected,'selection_report':report,'selection_method':'关键词初筛、方法相关性模型复核、主题多样性、原文摘要生成与二次核验'}
    validate(issue);assert_unseen(issue,records)
    if output:save_json(Path(output),issue)
    if dry_run:print('Live pipeline verified; published editions unchanged');return
    # Exclusive creation makes a duplicate/manual rerun unable to overwrite history.
    with path.open('x') as f:json.dump(issue,f,ensure_ascii=False,indent=2);f.write('\n')
    build()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dry-run',action='store_true');p.add_argument('--output');p.add_argument('--discover-only',action='store_true')
    a=p.parse_args();run(a.dry_run,a.output,a.discover_only)
