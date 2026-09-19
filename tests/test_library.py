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
        review = {'accept': True, 'topic': 'cognition', 'kind': '计算方法', 'reason': '研究人的认知模型'}
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
        papers = sources.crossref_rows([item], self.today)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]['published'], '2026-08')
        item['update-to'] = [{'type': 'retraction'}]
        self.assertEqual(sources.crossref_rows([item], self.today), [])

    def test_historical_papers_have_no_two_year_cutoff(self):
        p=copy.deepcopy(self.data['papers'][0]);p['published']='1998'
        p['_abstract']='This computational model explains human cognition and mental states. '*10
        self.assertTrue(sources.eligible(p,self.today))
        p['published']='2099'
        self.assertFalse(sources.eligible(p,self.today))

    def test_arxiv_metadata_preserves_status_and_versions(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/1306.5279v2</id><title>Emotion modeling for human interaction</title><published>2013-06-22T00:00:00Z</published><author><name>Researcher</name></author><x:doi>10.1234/formal</x:doi><x:journal_ref>Nature 2026</x:journal_ref><summary>'''+'We model human emotional states and predict social behavior. '*10+'''</summary></entry></feed>'''
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
            'descriptions':[{'descriptionType':'Abstract','description':'We model human emotional states and predict social behavior. '*10}],
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
