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
        for name in ('Nature Fake Journal', 'Science Fiction', 'Advanced Electromagnetics', 'arXiv', 'ACL Fake Journal'):
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

if __name__ == '__main__':
    unittest.main()
