import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import core,build,sources,summarize,update
from summarize import valid_brief,normalize_brief

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.issue=json.loads(next(core.DATA.glob('*.json')).read_text())
    def test_identity_survives_doi_spelling_and_arxiv_versions(self):
        a={'title':'Same: A Human Model','url':'https://arxiv.org/abs/2606.11482v1','doi':'https://doi.org/10.1234/ABC'}
        b={'title':'Same — A Human Model','url':'https://arxiv.org/pdf/2606.11482v3','doi':'10.1234/abc'}
        self.assertGreaterEqual(len(core.keys(a)&core.keys(b)),3)
    def test_preprint_and_formal_version_alias_deduplication(self):
        p=copy.deepcopy(self.issue['papers'][0]);p['doi_aliases']=['10.48550/arxiv.1234.56789']
        records=[{'keys':list(core.keys(p))}]
        duplicate=copy.deepcopy(p);duplicate['title']='Retitled conference paper';duplicate['doi']='10.48550/arxiv.1234.56789';duplicate['url']='https://arxiv.org/abs/1234.56789'
        with self.assertRaises(ValueError):core.assert_unseen({'papers':[duplicate]},records)
    def test_future_and_duplicate_papers_rejected(self):
        broken=copy.deepcopy(self.issue);broken['papers'][1]=copy.deepcopy(broken['papers'][0])
        with self.assertRaises(ValueError):core.validate(broken)
        broken=copy.deepcopy(self.issue);broken['papers'][0]['published']='2099-01-01'
        with self.assertRaises(ValueError):core.validate(broken)
    def test_source_precision_and_invalid_urls(self):
        self.assertEqual(core.date_floor('2026-07'),dt.date(2026,7,1))
        for u in ('javascript:alert(1)','https://user:password@example.com/','http://example.com'):
            with self.assertRaises(ValueError):core.safe_url(u)
    def test_unrelated_sources_excluded(self):
        p={'published':'2026-08-01','_abstract':'We propose a neural model for learning state transitions. '+'This system predicts complex physical dynamics from video observations and uses a computational model. '*8}
        for title in ('A Physical World Model for Driving','Technical Report: Emotional Intelligence','A Survey of Theory of Mind in Language Models'):
            self.assertFalse(sources.eligible({**p,'title':title},dt.date(2026,9,17)))
        self.assertTrue(sources.eligible({**p,'title':'Bayesian Inference of Human Intentions'},dt.date(2026,9,17)))
    def test_acl_preserves_publication_month_and_nested_title(self):
        abstract='We propose a computational model of human emotional appraisal and evaluate it in experiments. '+'The model uses language models to infer emotional states and their transitions in conversations. '*5
        xml=f'<collection id="2026.acl"><volume id="long"><meta><year>2026</year><month>July</month></meta><paper id="1"><title><fixed-case>LLM</fixed-case> Emotional Appraisal</title><author><first>A</first><last>Researcher</last></author><abstract>{abstract}</abstract><doi>10.1234/example</doi></paper></volume></collection>'
        p=sources.acl_xml(xml,dt.date(2026,9,17))[0]
        self.assertEqual(p['published'],'2026-07');self.assertEqual(p['title'],'LLM Emotional Appraisal');self.assertEqual(p['url'],'https://aclanthology.org/2026.acl-long.1/')
    def test_brief_requires_every_method_field(self):
        good={f:'中文说明用于研究人的情绪信念和内在心理状态。'*2 for f in core.FIELDS}
        self.assertTrue(valid_brief(good));good['method']=''
        self.assertFalse(valid_brief(good))
    def test_invalid_brief_is_repaired_with_source_and_field_feedback(self):
        good={f:'中文说明用于研究人的情绪信念和内在心理状态。'*2 for f in core.FIELDS}
        bad={**good,'target':'人格'}
        p={'title':'PsyPath','_abstract':'We propose a model of human personality.'}
        with patch.object(summarize,'request',side_effect=[good,bad,good]) as request:
            self.assertEqual(summarize.summarize('local',p),good)
            self.assertEqual(request.call_count,3)
            self.assertIn('target',request.call_args.args[2])
            self.assertIn(p['_abstract'],request.call_args.args[2])
    def test_repeated_invalid_brief_still_fails_quality_gate(self):
        bad={f:'太短' for f in core.FIELDS}
        with patch.object(summarize,'request',return_value=bad) as request:
            with self.assertRaisesRegex(ValueError,'Invalid Chinese method brief'):
                summarize.summarize('local',{'title':'Example','_abstract':'A study.'})
            self.assertEqual(request.call_count,4)
    def test_bad_candidate_is_replaced_without_losing_verified_briefs(self):
        candidates=[{'title':str(i),'topic':topic,'_abstract':'Source abstract'} for i,topic in enumerate(['emotion','mind','world','person'])]
        brief={f:'中文说明用于研究人的情绪信念和内在心理状态。'*2 for f in core.FIELDS}
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'assess',side_effect=lambda base,p:{'accept':True,'topic':p['topic'],'reason':'方法'}), patch.object(update,'summarize',side_effect=[brief,ValueError('bad target'),brief,brief]) as generate:
            papers=update.make_briefs('local',candidates,Path(tmp))
            self.assertEqual([p['title'] for p in papers],['0','2','3'])
            self.assertEqual(generate.call_count,4)
            self.assertTrue(all('_abstract' not in p for p in papers))
            self.assertTrue(all('_abstract' in p for p in candidates))
            audit=json.loads((Path(tmp)/'selection-review.json').read_text())
            self.assertEqual(audit[1]['brief_status'],'rejected')
            self.assertEqual(audit[1]['brief_error'],'bad target')
    def test_brief_failures_are_bounded_and_audited(self):
        candidates=[{'title':str(i),'topic':'emotion','_abstract':'Source'} for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'assess',return_value={'accept':True,'topic':'emotion','reason':'方法'}), patch.object(update,'summarize',side_effect=ValueError('bad brief')) as generate:
            with self.assertRaisesRegex(RuntimeError,'keep previous issue'):
                update.make_briefs('local',candidates,Path(tmp))
            self.assertEqual(generate.call_count,6)
            self.assertEqual(json.loads((Path(tmp)/'preview.json').read_text()),[])
            self.assertEqual(len(json.loads((Path(tmp)/'selection-review.json').read_text())),6)
    def test_model_internal_optimization_is_not_human_mental_modeling(self):
        for title in [
            'Question Tells You Where the Answer Is: Intention-aware Long-Context KV Cache Compression',
            'When Correct Beliefs Collapse: Epistemic Resilience of LLMs under Clinical Pressure',
            'Vulnerability of LLMs’ Stated Belief? LLMs Belief Resistance Check Through Strategic Persuasive Conversation Interventions',
        ]:
            self.assertTrue(sources.off_scope_reason({'title':title}))
        for title in ['Sentipolis: Emotion-Aware Agents for Social Simulations','LLM-based Theory of Mind for Human Belief Inference']:
            self.assertFalse(sources.off_scope_reason({'title':title}))
    def test_benchmark_comparison_does_not_count_as_new_method(self):
        abstract=('We introduce MOSAIC, a controlled benchmark for theory of mind and social action. '
                  'We evaluate language models in cooperative scenarios. '
                  'An existing model included as a structured architectural reference succeeds on these tasks.')
        self.assertFalse(sources.has_method_contribution(abstract))
        self.assertTrue(sources.has_method_contribution(abstract+' We further propose a new computational framework for belief inference.'))
    def test_emotion_word_does_not_turn_content_filter_into_mental_model(self):
        p={'title':'Emotion-Aware Cyberbullying Detection for Mental Health','published':'2026-09-09',
           '_abstract':'This paper presents a neural framework for classifying cyberbullying content. '+
           'The approach uses language models and emotion filters to identify harmful messages and improve computational efficiency. '*4}
        self.assertFalse(sources.eligible(p,dt.date(2026,9,17)))
        p['title']='Theory of Mind and Human Intention Inference for Contextual Hate Speech'
        p['_abstract']='We propose a computational model of human intentions and beliefs. '+p['_abstract']
        self.assertTrue(sources.eligible(p,dt.date(2026,9,17)))
    def test_necessary_is_not_substituted_for_sufficient(self):
        draft={f:'中文说明用于研究人的情绪信念和内在心理状态。'*2 for f in core.FIELDS}
        draft['evidence']='实验结果说明明确的信念行动耦合是任务成功的必要条件。'
        with self.assertRaises(ValueError):normalize_brief(draft,'Explicit belief-action coupling is sufficient for this task.')
        draft['evidence']='当前实验结果支持这一方法的有效性，但不能推广到所有情境。'
        draft['title_zh']='评估引导的理论心智建模'
        self.assertEqual(normalize_brief(draft,'appraisal-guided theory of mind')['title_zh'],'认知评价引导的心智理论建模')
        draft['method']='使用变压器模型对心理状态进行计算建模。'
        self.assertIn('Transformer',normalize_brief(draft,'transformer models')['method'])
    def test_archive_is_immutable_and_html_is_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data/issues';site=root/'site';data.mkdir(parents=True);site.mkdir()
            for name in ('style.css','reading.js'):(site/name).write_text((core.SITE/name).read_text())
            issue=copy.deepcopy(self.issue);issue['papers'][0]['title_zh']='<script>中文标题</script>'
            core.save_json(data/f'{issue["date"]}.json',issue)
            with patch.object(build,'ROOT',root),patch.object(build,'DATA',data),patch.object(build,'SITE',site),patch.object(core,'ROOT',root),patch.object(core,'DATA',data):
                build.build();archive=site/'archive'/f'{issue["date"]}.html';old=archive.read_bytes()
                self.assertIn('&lt;script&gt;中文标题',old.decode())
                (site/'style.css').write_text('body{color:red}');build.build()
                self.assertEqual(old,archive.read_bytes())
                self.assertIn('body{color:red}',(site/'index.html').read_text())

if __name__=='__main__':unittest.main()
