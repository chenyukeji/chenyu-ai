import importlib.util
import copy
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-yunying/skills/chenyu-listing/scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


extractor = module('extract_development_brief')
analyzer = module('analyze_listing')
package_validator = module('validate_listing_package')


class ListingTests(unittest.TestCase):
    @staticmethod
    def listing_package():
        return {
            'targets': ['DE'],
            'variants': [{'id': 'V1'}],
            'facts': [{'id': 'F1', 'source_type': 'own_product', 'status': 'confirmed',
                       'field': 'material', 'value': 'Papier', 'variant_ids': ['V1'],
                       'source': {'sheet': 'Product', 'cell': 'B2'}}],
            'mappings': [{'marketplace': 'DE', 'variant_id': 'V1', 'fact_ids': ['F1'],
                          'buying_reasons': ['Leicht'], 'keywords': ['Dekoration'],
                          'listing_fields': ['title', 'bullet_1']}],
            'listings': [{'marketplace': 'DE', 'language': 'de-DE', 'variant_id': 'V1',
                          'title': 'Dekoration aus Papier',
                          'bullets': ['Punkt eins', 'Punkt zwei', 'Punkt drei', 'Punkt vier', 'Punkt fünf'],
                          'description': ('Eine Dekoration aus Papier.\n\nEigenschaften:\n'
                                          '1. Leicht: Einfach zu platzieren.\n'
                                          '2. Form: Dekorative Gestaltung.\n'
                                          '3. Anlass: Für Feiern geeignet.\n\n'
                                          'Produktdetails:\nMaterial: Papier\nFarbe: Weiß\nGröße: 10 cm\n\n'
                                          'Lieferumfang:\n1 × Dekoration'),
                          'search_terms': 'dekoration feier papier', 'claim_fact_ids': ['F1']}],
        }

    def test_xlsx_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'sample.xlsx', Path(tmp) / 'out'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Product" sheetId="1" r:id="r1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml', '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheetData><row r="1">
                <c r="A1" t="inlineStr"><is><t>https://example.com/a https://example.com/b</t></is></c>
                <c r="B1"><f>HYPERLINK("https://example.com/c","ref")</f></c>
                <c r="C1"><f>HYPERLINK(A2,"dynamic")</f></c>
                </row></sheetData><mergeCells><mergeCell ref="A2:B2"/></mergeCells><hyperlinks><hyperlink ref="D1" r:id="h1"/></hyperlinks></worksheet>''')
                z.writestr('xl/worksheets/_rels/sheet1.xml.rels', '<Relationships><Relationship Id="h1" Target="https://example.com/d" TargetMode="External"/></Relationships>')
                z.writestr('xl/embeddings/object.bin', b'not executable')
            result = extractor.extract(source, out)
            self.assertEqual(len(result['links']), 4)
            self.assertEqual(result['links'][-1]['cell'], 'D1')
            self.assertEqual(result['sheets'][0]['merged_ranges'], ['A2:B2'])
            self.assertTrue(any('Dynamic HYPERLINK' in w for w in result['warnings']))
            self.assertEqual(len(result['attachments']), 1)
            with self.assertRaises(ValueError):
                extractor.extract(source, out)

    def test_frequency_union_and_language(self):
        records = [dict(id='a', marketplace='DE', product_group='p1', status='complete', title='Baumschmuck Baumschmuck'),
                   dict(id='b', marketplace='DE', product_group='p1', status='partial', title='Baumdeko'),
                   dict(id='c', marketplace='DE', product_group='p2', status='partial', title='Baumdeko'),
                   dict(id='d', marketplace='FR', product_group='p3', status='complete', title='Baumschmuck'),
                   dict(id='e', marketplace='DE', product_group='p4', status='failed', title='Baumschmuck')]
        report = analyzer.analyze({'competitors': records, 'keywords': [dict(marketplace='DE', phrase='Baumschmuck', aliases=['Baumdeko'])]})
        kw = report['keyword_frequency'][0]
        self.assertEqual((kw['exact_groups'], kw['semantic_groups'], kw['sample_groups']), (1, 2, 2))
        self.assertEqual(kw['field_sample_groups']['description'], 0)

    def test_checks_and_unicode(self):
        phrase = 'one two three four five six seven eight'
        result = analyzer.analyze({'brands': ['ExampleBrand'],
            'competitors': [dict(id='c', marketplace='UK', product_group='p', status='complete', title=phrase)],
            'keywords': [dict(marketplace='UK', phrase='one')],
            'listings': [dict(marketplace='UK', title=phrase + ' ExampleBrand [Brand] B012345678', bullets=[], description='', search_terms='é')],
            'limits': {'UK': {'search_terms_bytes': 1}}})['listing_reviews'][0]
        self.assertEqual(result['lengths']['search_terms_bytes'], 2)
        self.assertEqual(len(result['overlap_review']), 1)
        self.assertIn('title_chars', result['unverified_limits'])
        self.assertTrue(any('exceeds' in i for i in result['issues']))
        self.assertIn('Brand placeholder', result['issues'])
        self.assertFalse(analyzer.contains('stone', 'one'))
        self.assertTrue(analyzer.contains('Étoile', 'étoile'))
        self.assertFalse(analyzer.contains('étoile', 'etoile'))

    def test_own_listing_package_ready(self):
        result = package_validator.validate(self.listing_package())
        self.assertTrue(result['ready_for_delivery'])
        self.assertEqual(result['coverage']['expected_listings'], 1)

    def test_own_listing_package_rejects_missing_or_competitor_facts(self):
        data = copy.deepcopy(self.listing_package())
        data['facts'][0]['source_type'] = 'competitor'
        data['facts'][0]['status'] = 'unconfirmed'
        data['listings'][0]['bullets'] = ['Only one']
        data['listings'][0]['description'] = 'Eigenschaften:\n1. A: B\nProduktdetails:\nLieferumfang:'
        data['listings'][0]['title'] += ' B012345678'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('not sourced from own_product' in error for error in result['errors']))
        self.assertTrue(any('five non-empty bullets' in error for error in result['errors']))
        self.assertTrue(any('uses non-confirmed fact' in error for error in result['errors']))
        self.assertTrue(any('contains an ASIN' in error for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
