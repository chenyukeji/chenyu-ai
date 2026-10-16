"""Validate published retrieval references against the preserved workbook records."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'plugins/chenyu-yunying/skills/chenyu-shensuxin'

class AppealReferenceIndexTests(unittest.TestCase):
    def test_every_representative_is_an_approved_complete_original(self):
        library=json.loads((ROOT/'references/workbook-cases.json').read_text())
        index=json.loads((ROOT/'references/retrieval-index.json').read_text())
        records={r['id']:r for r in library['records']}
        self.assertEqual(len(index['families']),len({f['id'] for f in index['families']}))
        for family in index['families']:
            self.assertTrue(family['keywords'])
            self.assertTrue(family['records'])
            for rid in family['records']:
                with self.subTest(record=rid):
                    self.assertNotIn(rid,index['excluded_records'])
                    record=records[rid]
                    self.assertIn(record['source_status'],('通过','已通过','申诉通过'))
                    self.assertTrue(library['letters'][record['letter_id']]['text'].strip())
        self.assertTrue(set(index['excluded_records']).issubset(records))
        for name in ('case-index.md','case-analysis.md','workbook-cases.json','retrieval-index.json'):
            self.assertIn('references/'+name,(ROOT/'SKILL.md').read_text())
