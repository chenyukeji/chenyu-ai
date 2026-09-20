import importlib.util
import copy
import tempfile
import unittest
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'plugins/chenyu-yunying/skills'
LISTING_ROOT = BASE / 'chenyu-listing/scripts'
YUNYING_ROOT = BASE / 'chenyu-yunying/scripts'


def module(name, root=LISTING_ROOT):
    spec = importlib.util.spec_from_file_location(name, root / (name + '.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


extractor = module('extract_development_brief', YUNYING_ROOT)
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
            'keywords': [
                {'marketplace': 'DE', 'phrase': 'Dekoration', 'aliases': ['Deko'], 'is_core': True},
                {'marketplace': 'DE', 'phrase': 'Papierdekoration', 'aliases': ['Dekoration aus Papier'], 'is_core': True},
                {'marketplace': 'DE', 'phrase': 'Festschmuck', 'aliases': ['Feierdeko'], 'is_core': True},
            ],
            'mappings': [{'marketplace': 'DE', 'variant_id': 'V1', 'fact_ids': ['F1'],
                          'buying_reasons': ['Leicht'],
                          'keywords': ['Dekoration', 'Papierdekoration', 'Festschmuck'],
                          'listing_fields': ['title', 'bullet_1', 'bullet_2', 'bullet_3']}],
            'listings': [{'marketplace': 'DE', 'language': 'de-DE', 'variant_id': 'V1',
                          'title_keywords': ['Dekoration', 'Papierdekoration', 'Festschmuck'],
                          'title_scene': 'für Feiern', 'title_quantity': 1,
                          'title_quantity_term': '', 'color_mode': 'not_applicable',
                          'title_color_terms': [],
                          'title': 'Dekoration, Papierdekoration und Festschmuck für Feiern',
                          'bullets': [
                              '📦【Klarer Lieferumfang】Der Lieferumfang ist auf die gewählte Variante abgestimmt und nennt die enthaltenen Dekorationsteile eindeutig. So lässt sich die geplante Anordnung vor dem Dekorieren besser einschätzen, während zusätzlich abgebildete Szenenartikel nicht mit dem Inhalt verwechselt werden.',
                              '🧩【Bestätigtes Papiermaterial】Die Dekoration besteht aus Papier und lässt sich dadurch gut in vorhandene saisonale Arrangements integrieren. Materialangaben bleiben in Titel, Beschreibung und Produktdetails einheitlich, ohne daraus unbestätigte Eigenschaften wie Wasserfestigkeit oder besondere Haltbarkeit abzuleiten.',
                              '✨【Flexibel kombinierbar】Die einzelnen Elemente können als ruhiger Akzent verwendet oder mit bereits vorhandener Tisch- und Raumdekoration kombiniert werden. Dadurch entsteht eine zusammenhängende Gestaltung, ohne dass zusätzliche, nicht enthaltene Accessoires als Bestandteil des Sets dargestellt werden.',
                              '🎉【Für festliche Arrangements】Die Gestaltung eignet sich für bestätigte Feiern und saisonale Innenraumdekorationen. Sie kann je nach Platzangebot auf geeigneten Flächen arrangiert werden und ergänzt unterschiedliche festliche Stilrichtungen, ohne einen bestimmten Aufbau vorzuschreiben.',
                              '💡【Sachgerechter Umgang】Verwenden Sie ausschließlich die im Lieferumfang genannten Teile und behandeln Sie die Papieroberfläche entsprechend dem bestätigten Material. Lagern Sie die Dekoration trocken und geschützt, damit Form und Erscheinungsbild zwischen den Einsätzen erhalten bleiben.',
                          ],
                          'description': ('<p>Eine Dekoration aus Papier für festliche Arrangements. '
                                          'Sie lässt sich einzeln oder zusammen mit vorhandenen Dekorationen einsetzen.</p>'
                                          '<p><b>Eigenschaften:</b><br>'
                                          '1. Leicht: Einfach zu platzieren.<br>'
                                          '2. Form: Dekorative Gestaltung.<br>'
                                          '3. Anlass: Für Feiern geeignet.</p>'
                                          '<p><b>Produktdetails:</b><br>Material: Papier<br>Farbe: Weiß<br>Größe: 10 cm</p>'
                                          '<p><b>Lieferumfang:</b><br>1 × Dekoration</p>'),
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
        data = self.listing_package()
        result = package_validator.validate(data)
        self.assertTrue(result['ready_for_delivery'])
        self.assertEqual(result['coverage']['expected_listings'], 1)
        self.assertTrue(any('editorial target' in warning for warning in result['warnings']))
        review = analyzer.analyze(data)['listing_reviews'][0]
        festschmuck = next(item for item in review['coverage']
                           if item['phrase'] == 'Festschmuck')
        self.assertTrue(festschmuck['selected_for_title'])
        self.assertIn('title', festschmuck['exact_locations'])

    def test_listing_package_rejects_unified_format_violations(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['bullets'][0] = 'Lieferumfang: Nur ein kurzer Satz.'
        data['listings'][0]['search_terms'] = 'dekoration, papier papier'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('bullet 1 must use' in error for error in result['errors']))
        self.assertTrue(any('must not contain punctuation' in error for error in result['errors']))
        self.assertTrue(any('repeats tokens: papier' in error for error in result['errors']))

    def test_listing_package_rejects_thin_bullet_copy(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['bullets'][0] = (
            '📦【Klarer Lieferumfang】Die ausgewählte Variante enthält die angegebenen '
            'Dekorationsteile. Dadurch lässt sich der Inhalt vor dem Dekorieren überblicken.'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('at least 180 visible characters' in error
                            for error in result['errors']))

    def test_listing_package_requires_three_core_title_keywords_and_scene(self):
        data = copy.deepcopy(self.listing_package())
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        data['keywords'][2]['is_core'] = False
        data['listings'][0]['title_scene'] = 'für Hochzeiten'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title keyword is not marked as core: Festschmuck' in error
                            for error in result['errors']))
        self.assertTrue(any('title does not contain title_scene: für Hochzeiten' in error
                            for error in result['errors']))

    def test_listing_package_requires_html_and_rejects_multicolor_title_terms(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['color_mode'] = 'multi'
        listing['title_color_terms'] = ['Rot']
        listing['title'] += ' Rot'
        listing['description'] = (
            'Eine Beschreibung. Eigenschaften: 1. Material: Papier. '
            '2. Form: Dekoration. 3. Anlass: Feiern. '
            'Produktdetails: Material: Papier. Lieferumfang: 1 Dekoration.'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('must not use title_color_terms when color_mode is multi' in error
                            for error in result['errors']))
        self.assertTrue(any('description must use basic HTML' in error
                            for error in result['errors']))

    def test_listing_package_rejects_bad_title_spacing_and_checks_optional_notices(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['title'] = 'Dekoration,Papierdekoration und Festschmuck für Feiern'
        listing['notice_fact_ids'] = ['F1']
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title uses non-standard punctuation spacing' in error
                            for error in result['errors']))
        self.assertTrue(any('must include localized notices' in error
                            for error in result['errors']))

    def test_title_quantity_is_omitted_for_one_and_precedes_first_keyword_for_multipacks(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['title_quantity'] = 12
        listing['title_quantity_term'] = '12 Stück'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title quantity must immediately precede' in error
                            for error in result['errors']))

        listing['title'] = '12 Stück Dekoration, Papierdekoration und Festschmuck für Feiern'
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

        listing['title_quantity'] = 1
        listing['title_quantity_term'] = '1 Stück'
        listing['title'] = '1 Dekoration, Papierdekoration und Festschmuck für Feiern'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title_quantity_term must be empty' in error
                            for error in result['errors']))
        self.assertTrue(any('title must omit quantity 1' in error
                            for error in result['errors']))

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
