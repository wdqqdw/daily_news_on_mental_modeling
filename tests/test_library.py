import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build
import library_core as lib
import library_sources as sources
import update_library as update
from core import ROOT, uid, keys, FIELDS

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.data = lib.load_library()
        self.today = dt.date(2026, 9, 20)

    def test_publication_groups_are_explicit(self):
        for name in ('Nature', 'Science', 'Cell'):
            self.assertEqual(lib.classify(name), 'main')
        for name in ('Nature Human Behaviour', 'Neuron', 'Science Advances', 'Communications Psychology'):
            self.assertEqual(lib.classify(name), 'family')
        for name in ('ICML 2026', 'Findings of ACL 2026', 'Journal of Artificial Intelligence Research'):
            self.assertEqual(lib.classify(name), 'ai')
        self.assertEqual(lib.classify('arXiv'),'arxiv')
        for name in ('Nature Fake Journal', 'Science Fiction', 'Advanced Electromagnetics', 'ACL Fake Journal'):
            self.assertIsNone(lib.classify(name))

    def test_initial_library_and_archive_identity(self):
        lib.validate_library(self.data)
        self.assertEqual({p['group'] for p in self.data['papers']}, set(lib.GROUPS))
        for file in (ROOT / 'data/issues').glob('*.json'):
            for old in json.loads(file.read_text())['papers']:
                match = next((p for p in self.data['papers'] if keys(old) & keys(p)), None)
                if match:
                    self.assertEqual(match['id'], uid(old))

    def test_zero_additions_preserve_collection_and_date(self):
        self.assertEqual(update.append(self.data, [], self.today), self.data)

    def test_versions_do_not_reappear(self):
        version = copy.deepcopy(self.data['papers'][0])
        version['url'] += '?version=2'
        self.assertEqual(update.append(self.data, [version], self.today), self.data)
        seen = set(keys(version))
        self.assertEqual(update.rank([version], seen, self.today), [])

    def test_failed_brief_keeps_other_valid_additions_without_quota(self):
        candidates = copy.deepcopy(self.data['papers'][:2])
        evidence='We compare human cognition with deep neural network representations.'
        for p in candidates:p['_abstract']=evidence
        review = {'accept': True, 'topic': 'cognition', 'kind': '计算方法', 'reason': '研究人的认知模型',
                  'deep_learning_related':True,'deep_learning_evidence':evidence}
        brief = {key: candidates[1][key] for key in FIELDS}
        with tempfile.TemporaryDirectory() as temp, patch.object(update, 'assess', return_value=review), patch.object(update, 'summarize', side_effect=[ValueError('invalid draft'), brief]):
            finished, audit = update.make_additions('model', candidates, self.today, Path(temp))
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]['id'], candidates[1]['id'])
        self.assertIn('error', audit[0])

    def test_infrastructure_failure_is_not_reported_as_no_new_papers(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(update, 'assess', side_effect=OSError('model offline')):
            with self.assertRaises(RuntimeError):
                update.make_additions('model', self.data['papers'][:1], self.today, Path(temp))

    def test_all_rejected_is_a_valid_empty_collection(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(update, 'assess', return_value={'accept': False}):
            finished, _ = update.make_additions('model', self.data['papers'][:1], self.today, Path(temp))
        self.assertEqual(finished, [])

    def test_build_does_not_modify_legacy_archives(self):
        before = {p: p.read_bytes() for p in (ROOT / 'site/archive').glob('*.html')}
        before[ROOT / 'site/archive.html'] = (ROOT / 'site/archive.html').read_bytes()
        build.build()
        self.assertTrue(all(path.read_bytes() == value for path, value in before.items()))

    def test_crossref_neural_evidence_and_date_precision(self):
        item = {'DOI': '10.1234/sample', 'type': 'journal-article', 'title': ['Human cognitive maps represent mental states'], 'container-title': ['Nature Neuroscience'], 'published': {'date-parts': [[2026, 8]]}, 'abstract': 'Participants represent beliefs in neural cognitive maps. ' + 'Observed brain responses support representations of human mental states. ' * 8}
        self.assertEqual(sources.crossref_rows([item], self.today), [])
        item['abstract']+='We compare these representations with deep neural networks.'
        papers = sources.crossref_rows([item], self.today)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]['published'], '2026-08')
        item['update-to'] = [{'type': 'retraction'}]
        self.assertEqual(sources.crossref_rows([item], self.today), [])

    def test_historical_papers_have_no_two_year_cutoff(self):
        p=copy.deepcopy(self.data['papers'][0]);p['published']='1998'
        p['_abstract']='This artificial neural network model explains human cognition and mental states. '*10
        self.assertTrue(sources.eligible(p,self.today))
        p['published']='2099'
        self.assertFalse(sources.eligible(p,self.today))

    def test_general_ai_scope_is_limited_to_named_nsc_journals(self):
        p={'title':'Efficient KV-cache compression for language models','published':'2026-09-01',
           'status':'published','_abstract':'We propose a deep learning architecture for efficient language model inference with experimental validation. '*8}
        for venue in ('Nature','Science','Cell','Nature Machine Intelligence','Nature Computational Science','Cell Systems','Cancer Cell'):
            self.assertTrue(sources.eligible({**p,'venue':venue},self.today),venue)
        for venue in ('arXiv','ICML 2026','Neuron','Scientific Reports','Communications Psychology','Nature Fake Journal','Science Fiction'):
            self.assertFalse(sources.eligible({**p,'venue':venue},self.today),venue)
        self.assertFalse(sources.eligible({**p,'venue':'Nature','published':'2099'},self.today))
        self.assertFalse(sources.eligible({**p,'venue':'Nature','title':'Author Correction: Efficient language models'},self.today))

    def test_biological_neural_and_classical_models_are_not_deep_learning(self):
        p={'title':'Modeling human emotional beliefs','published':'2025-03-01','status':'published'}
        for venue in ('Nature','Nature Neuroscience','ICML 2025','arXiv'):
            p.update(venue=venue,status='preprint' if venue=='arXiv' else 'published')
            for abstract in ('Human neural activity explains emotional learning and beliefs. ',
                             'We fit Bayesian models and statistical regressions to human beliefs. '):
                self.assertFalse(sources.eligible({**p,'_abstract':abstract*10},self.today),venue)
            for abstract in ('We use LLM agents to simulate human emotional beliefs. ',
                             'We compare human beliefs with CNN representations in behavioral experiments. ',
                             'We compare human emotional learning with multilayer perceptrons in behavioral experiments. '):
                self.assertTrue(sources.eligible({**p,'_abstract':abstract*10},self.today),venue)

    def test_missing_or_invented_deep_learning_evidence_cannot_be_admitted(self):
        p=copy.deepcopy(self.data['papers'][0])
        p['_abstract']='We compare human cognition with deep neural network representations.'
        review={'accept':True,'topic':'cognition','kind':'计算方法','reason':'模型比较',
                'deep_learning_related':True,'deep_learning_evidence':p['_abstract']}
        for changes in ({'deep_learning_related':None},{'deep_learning_evidence':''},
                        {'deep_learning_evidence':'We train an unrelated transformer for behavior prediction.'}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as temp, \
                 patch.object(update,'assess',return_value={**review,**changes}),patch.object(update,'summarize') as summarizer:
                with self.assertRaises(RuntimeError):update.make_additions('model',[p],self.today,Path(temp))
                summarizer.assert_not_called()
        self.assertTrue(update.verify_deep_learning_link(review,p))

    def test_no_deep_learning_link_is_normal_rejection_even_for_nsc(self):
        p=copy.deepcopy(self.data['papers'][0])
        p['_abstract']='A questionnaire study of human emotional responses. Deep learning may inspire future work.'
        review={'accept':True,'topic':'emotion','kind':'表征与行为证据','reason':'仅有未来工作的泛泛联系',
                'deep_learning_related':False,'deep_learning_evidence':''}
        with tempfile.TemporaryDirectory() as temp,patch.object(update,'assess',return_value=review),patch.object(update,'summarize') as summarizer:
            finished,audit=update.make_additions('model',[p],self.today,Path(temp))
        self.assertEqual(finished,[]);self.assertFalse(audit[0]['accept']);self.assertNotIn('error',audit[0])
        summarizer.assert_not_called()

    def test_recent_ai_gets_newest_first_without_displacing_history_and_mind(self):
        pool=[]
        for i,(t,date) in enumerate([('ai','2026-01-01'),('mind','2026-09-01'),('ai','2026-09-19'),('mind','2010')]):
            p=copy.deepcopy(self.data['papers'][0]);p.update(title=f'Example model {i}',doi=f'10.1234/rank{i}',url=f'https://example.org/rank{i}',venue='Nature',group='main',topic=t,published=date)
            pool.append(p)
        ranked=update.rank(pool,set(),self.today)
        self.assertEqual(ranked[0]['published'],'2026-09-19')
        self.assertEqual(ranked[1]['_lane'],'history')
        self.assertEqual(ranked[2]['topic'],'mind')

    def test_abstract_fallback_requires_exact_doi(self):
        rows=[{'DOI':'10.1234/a','title':['A deep learning model']}]
        response={'resultList':{'result':[
            {'doi':'10.1234/other','abstractText':'Wrong abstract','source':'MED','id':'1'},
            {'doi':'10.1234/a','abstractText':'Correct abstract','source':'MED','id':'2','pubTypeList':{'pubType':['Journal Article']}}]}}
        with patch.object(sources,'fetch',return_value=json.dumps(response)):
            result=sources.fill_ai_abstracts(rows)
        self.assertEqual(result[0]['abstract'],'Correct abstract')
        self.assertEqual(result[0]['_abstract_source'],'https://europepmc.org/article/MED/2')

    def test_publisher_fallback_does_not_read_related_papers(self):
        page='<meta name="citation_doi" content="10.1038/test"><section data-title="Abstract"><p>Verified abstract.</p></section><section>Unrelated reference.</section>'
        self.assertEqual(sources.nature_abstract(page,'10.1038/test'),'Verified abstract.')
        self.assertEqual(sources.nature_abstract(page,'10.1038/other'),'')
        self.assertEqual(sources.nature_abstract(page.replace('data-title="Abstract"','data-title="References"'),'10.1038/test'),'')

    def test_new_ai_search_keeps_human_and_arxiv_channels(self):
        calls=[]
        def capture(*args,**kwargs):calls.append(args);return [],0
        with patch.object(sources,'get_arxiv',return_value=([],0)),patch.object(sources,'crossref',side_effect=capture),patch.object(sources,'get_acl',return_value=[]):
            _,report=sources.collect(self.today)
        ai_calls=[c for c in calls if len(c)==7 and c[-1] is True]
        self.assertEqual(len(ai_calls),len(lib.NSC_AI_JOURNALS))
        self.assertTrue(all(c[3]==str(self.today-dt.timedelta(days=180)) for c in ai_calls))
        update.validate_source_coverage(report)
        report['successful_sources']=[s for s in report['successful_sources'] if not s.startswith('Journal AI recent:')]
        with self.assertRaises(RuntimeError):update.validate_source_coverage(report)

    def test_arxiv_metadata_preserves_status_and_versions(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/1306.5279v2</id><title>Emotion modeling for human interaction</title><published>2013-06-22T00:00:00Z</published><author><name>Researcher</name></author><x:doi>10.1234/formal</x:doi><x:journal_ref>Nature 2026</x:journal_ref><summary>'''+'We use deep neural networks to model human emotional states and predict social behavior. '*10+'''</summary></entry></feed>'''
        rows,_=sources.arxiv_rows(xml,self.today)
        self.assertEqual(rows[0]['arxiv_id'],'1306.5279')
        self.assertEqual(rows[0]['status'],'preprint')
        self.assertEqual(rows[0]['doi_aliases'],['10.1234/formal'])
        self.assertEqual(rows[0]['venue'],'arXiv')
        withdrawn=xml.replace('</entry>','<x:comment>This paper has been withdrawn.</x:comment></entry>')
        self.assertEqual(sources.arxiv_rows(withdrawn,self.today)[0],[])

    def test_recent_and_history_alternate_in_review_queue(self):
        pool=[]
        for i in range(8):
            p=copy.deepcopy(self.data['papers'][0]);p.update(title=f'Human emotion model {i}',url=f'https://example.org/{i}',doi=f'10.1234/{i}',published='2026-09-01' if i<4 else '2010')
            pool.append(p)
        ranked=update.rank(pool,set(),self.today)
        self.assertEqual([p['_lane'] for p in ranked[:6]],['recent','history']*3)
        reviews={uid(ranked[0]):{'reviewed_at':'2026-09-19','error':False}}
        self.assertNotIn(uid(ranked[0]),[uid(p) for p in update.rank(pool,set(),self.today,reviews)])

    def test_arxiv_history_query_paginates_beyond_recent_year(self):
        from urllib.parse import urlsplit,parse_qs
        query=parse_qs(urlsplit(sources.arxiv_query(['mental world model'],self.today,'history',120)).query)
        self.assertIn('199101010000 TO 202509192359',query['search_query'][0])
        self.assertEqual(query['start'],['120'])
        self.assertEqual(query['sortBy'],['relevance'])

    def test_arxiv_and_formal_aliases_keep_reading_identity(self):
        p=copy.deepcopy(self.data['papers'][0]);old_id=p['id']
        version=copy.deepcopy(p);version.update(title='Updated formal title for the same research',doi='10.1234/new-formal-version')
        enriched=update.enrich_identities({'version':2,'updated':self.data['updated'],'papers':[p]},[version])
        self.assertEqual(enriched['papers'][0]['id'],old_id)
        formal={**version,'url':'https://example.org/formal'}
        self.assertEqual(update.rank([formal],keys(enriched['papers'][0]),self.today),[])

    def test_historical_pages_advance_even_without_eligible_results(self):
        with patch.object(sources,'get_arxiv',return_value=([],200)),patch.object(sources,'crossref',return_value=([],200)),patch.object(sources,'get_acl',return_value=[]):
            _,report=sources.collect(self.today)
        values=report['_next_state']['pages']
        self.assertTrue(all(value==60 for key,value in values.items() if key.startswith('arxiv:')))
        self.assertTrue(all(value==70 for key,value in values.items() if key.startswith('crossref')))

    def test_arxiv_recent_and_history_must_both_be_checked(self):
        with self.assertRaises(RuntimeError):
            update.validate_source_coverage({'successful_sources':['arXiv history mind','ACL: 2026.acl']})
        with self.assertRaises(RuntimeError):
            update.validate_source_coverage({'successful_sources':['arXiv recent mind']})
        update.validate_source_coverage({'successful_sources':['arXiv recent mind','arXiv history mind']})

    def test_recent_arxiv_queries_stay_short(self):
        for terms in sources.ARXIV_THEMES.values():
            self.assertLess(len(sources.arxiv_query(terms,self.today)),1800)

    def test_datacite_arxiv_uses_first_submission_not_doi_registration(self):
        item={'attributes':{'doi':'10.48550/arxiv.1306.5279','state':'findable','url':'https://arxiv.org/abs/1306.5279',
            'titles':[{'title':'Emotion modeling for human social interaction'}],
            'descriptions':[{'descriptionType':'Abstract','description':'We use deep neural networks to model human emotional states and predict social behavior. '*10}],
            'publicationYear':2013,'created':'2026-09-20T00:00:00Z',
            'dates':[{'dateType':'Submitted','date':'2015-01-01'},{'dateType':'Submitted','date':'2013-06-22T01:02:03Z'}],
            'relatedIdentifiers':[{'relatedIdentifierType':'DOI','relationType':'IsVersionOf','relatedIdentifier':'10.1234/formal'},
                                  {'relatedIdentifierType':'DOI','relationType':'References','relatedIdentifier':'10.1234/cited'}]}}
        rows=sources.datacite_arxiv_rows([item],self.today,'history')
        self.assertEqual(rows[0]['published'],'2013-06-22')
        self.assertEqual(rows[0]['doi_aliases'],['10.1234/formal'])
        self.assertEqual(rows[0]['status'],'preprint')
        self.assertEqual(sources.datacite_arxiv_rows([item],self.today,'recent'),[])
        item['attributes']['url']='https://example.com/abs/1306.5279'
        self.assertEqual(sources.datacite_arxiv_rows([item],self.today,'history'),[])

    def test_fallback_keeps_independent_pagination_and_records_provenance(self):
        with patch.object(sources,'get_arxiv',side_effect=RuntimeError('HTTP 406')),patch.object(sources,'get_datacite_arxiv',return_value=([],200)) as fallback:
            result=sources.discover_arxiv(['emotion'],self.today,'history',120,60)
        fallback.assert_called_once_with(['emotion'],self.today,'history',60)
        self.assertEqual(result[2:4],('datacite','HTTP 406'))
        with patch.object(sources,'get_arxiv',side_effect=RuntimeError('HTTP 406')),patch.object(sources,'get_datacite_arxiv',return_value=([],200)),patch.object(sources,'crossref',return_value=([],0)),patch.object(sources,'get_acl',return_value=[]):
            _,report=sources.collect(self.today)
        self.assertEqual(len(report['fallback_sources']),9)
        self.assertTrue(any(key.startswith('datacite:') for key in report['_next_state']['pages']))
        self.assertFalse(any(key.startswith('arxiv:') for key in report['_next_state']['pages']))
        update.validate_source_coverage(report)
        report['unavailable_sources']=['arXiv recent world: both services failed']
        with self.assertRaises(RuntimeError):update.validate_source_coverage(report)

if __name__ == '__main__':
    unittest.main()
