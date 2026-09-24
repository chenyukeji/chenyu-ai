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
                          'title_color_terms': [], 'critical_differentiators': [],
                          'title': ('Dekoration, Papierdekoration und Festschmuck für Feiern '
                                    'und Feiertage'),
                          'item_highlights': ('Papiermaterial mit klarer Form für Tisch, Regal und '
                                              'Innenraum, einzeln platzierbar oder mit vorhandener '
                                              'Festdeko kombinierbar'),
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
                                          '1. Platzierung: Die Papierdekoration lässt sich auf geeigneten Flächen gezielt anordnen. Sie ergänzt vorhandene Arrangements, ohne zusätzlich abgebildete Gegenstände als Lieferumfang darzustellen.<br>'
                                          '2. Gestaltung: Die klare Form setzt einen sichtbaren dekorativen Akzent. Sie kann einzeln stehen oder mit abgestimmten Elementen kombiniert werden.<br>'
                                          '3. Anlass: Die Gestaltung ist für bestätigte Feiern und saisonale Innenräume vorgesehen. Der verfügbare Platz bestimmt, ob sie einzeln oder als Teil eines größeren Arrangements verwendet wird.</p>'
                                          '<p><b>Produktdetails:</b><br>Material: Papier<br>Farbe: Weiß<br>Größe: 10 cm</p>'
                                          '<p><b>Lieferumfang:</b><br>1 × Dekoration</p>'),
                          'search_terms': 'dekoartikel schmuckanhänger festbedarf',
                          'front_end_attributes': [],
                          'claim_fact_ids': ['F1']}],
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

    def test_competitor_evidence_requires_references_for_all_listing_fields(self):
        data = self.listing_package()
        data['competitors'] = [{'id': 'C1', 'marketplace': 'DE', 'product_group': 'P1',
                                'status': 'complete', 'asin': 'B012345678',
                                'title': 'Dekoartikel Schmuckanhänger Festbedarf'}]
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title_reference is required' in error for error in result['errors']))
        self.assertTrue(any('item_highlights_reference is required' in error
                            for error in result['errors']))
        self.assertTrue(any('description_reference is required' in error for error in result['errors']))
        self.assertTrue(any('search_terms_reference is required' in error for error in result['errors']))
        self.assertTrue(any('bullet_references must contain five' in error for error in result['errors']))

        listing = data['listings'][0]
        listing['title_reference'] = '参考 B012345678 标题'
        listing['item_highlights_reference'] = '参考 B012345678 标题及第2点'
        listing['bullet_references'] = [f'参考 B012345678 第{i}点' for i in range(1, 6)]
        listing['description_reference'] = '参考 B012345678 第1-5点'
        listing['search_terms_reference'] = '参考 B012345678 标题及五点'
        listing['primary_reference_asin'] = 'B012345678'
        data['search_term_audits'] = [
            {
                'marketplace': 'DE', 'variant_id': 'V1',
                'phrase': 'dekoartikel schmuckanhänger festbedarf',
                'source_asin': 'B012345678',
                'source_tool': 'sellersprite_reverse_asin',
                'source_marketplace': 'DE',
                'organic_results_checked': 20, 'relevant_results': 16,
                'relevance_band': 'high', 'decision': 'adopt',
                'local_volume_claimed': False,
            },
            {
                'marketplace': 'DE', 'variant_id': 'V1',
                'phrase': 'dekoartikel schmuckanhänger',
                'source_asin': 'B012345678',
                'source_tool': 'reference_title_terms',
                'source_field': 'title', 'source_marketplace': 'DE',
                'organic_results_checked': 20, 'relevant_results': 15,
                'relevance_band': 'high', 'decision': 'adopt',
                'local_volume_claimed': False,
            },
        ]
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

        data['search_term_audits'] = data['search_term_audits'][:1]
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('requires synonym candidates from reference listing titles' in error
                            for error in result['errors']))

    def test_listing_package_rejects_internal_variant_codes_in_buyer_copy(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['item_highlights'] = (
            'Design A: Papiermaterial mit klarer Form für Tisch, Regal und Innenraum, '
            'einzeln platzierbar oder mit Festdeko kombinierbar'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('contains internal variant codes' in error
                            for error in result['errors']))

        data['listings'][0]['buyer_visible_variant_terms'] = ['Design A']
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

    def test_listing_package_requires_all_adopted_incremental_tokens(self):
        data = copy.deepcopy(self.listing_package())
        data['competitors'] = [{
            'id': 'C1', 'marketplace': 'DE', 'product_group': 'P1',
            'status': 'complete', 'asin': 'B012345678',
            'title': 'Dekoartikel Schmuckanhänger Festbedarf Wintermotiv',
        }]
        listing = data['listings'][0]
        listing.update({
            'title_reference': '参考 B012345678 标题',
            'item_highlights_reference': '参考 B012345678 标题',
            'bullet_references': ['参考 B012345678' for _ in range(5)],
            'description_reference': '参考 B012345678',
            'search_terms_reference': '参考 B012345678 标题及卖家精灵反查',
            'primary_reference_asin': 'B012345678',
        })
        data['search_term_audits'] = [
            {
                'marketplace': 'DE', 'variant_id': 'V1',
                'phrase': 'dekoartikel schmuckanhänger festbedarf',
                'source_asin': 'B012345678',
                'source_tool': 'sellersprite_reverse_asin',
                'source_marketplace': 'DE',
                'organic_results_checked': 20, 'relevant_results': 16,
                'relevance_band': 'high', 'decision': 'adopt',
                'local_volume_claimed': False,
            },
            {
                'marketplace': 'DE', 'variant_id': 'V1',
                'phrase': 'wintermotiv', 'source_asin': 'B012345678',
                'source_tool': 'reference_title_terms', 'source_field': 'title',
                'source_marketplace': 'DE',
                'organic_results_checked': 20, 'relevant_results': 15,
                'relevance_band': 'high', 'decision': 'adopt',
                'local_volume_claimed': False,
            },
        ]
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('omits audited incremental tokens: wintermotiv' in error
                            for error in result['errors']))

        listing['search_terms'] += ' wintermotiv'
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

    def test_listing_package_rejects_unified_format_violations(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['bullets'][0] = 'Lieferumfang: Nur ein kurzer Satz.'
        data['listings'][0]['search_terms'] = 'dekoration, papier papier'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('bullet 1 must use' in error for error in result['errors']))
        self.assertTrue(any('must not contain punctuation' in error for error in result['errors']))
        self.assertTrue(any('repeats tokens: papier' in error for error in result['errors']))

    def test_listing_package_enforces_incremental_search_terms(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['search_terms'] = 'Dekoartikel und Papier ' + ('ä' * 120)
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('must be lowercase' in error for error in result['errors']))
        self.assertTrue(any('contains stop words: und' in error for error in result['errors']))
        self.assertTrue(any('repeats front-end tokens: papier' in error for error in result['errors']))
        self.assertTrue(any('UTF-8 bytes' in error for error in result['errors']))

    def test_item_highlights_is_required_and_included_in_front_end_deduplication(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['item_highlights'] = ''
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('item_highlights is empty' in error for error in result['errors']))

        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['search_terms'] = 'innenraum'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('repeats front-end tokens: innenraum' in error
                            for error in result['errors']))

    def test_same_product_evidence_is_a_valid_confirmed_fact_source(self):
        data = copy.deepcopy(self.listing_package())
        fact = data['facts'][0]
        fact['source_type'] = 'same_product_evidence'
        fact['same_product_confirmed'] = True
        fact['source'] = {
            'asin': 'B012345678', 'field': 'bullet_2', 'user_message': '同款确认'
        }
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

        fact['same_product_confirmed'] = False
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('lacks explicit same-product confirmation' in error
                            for error in result['errors']))

    def test_bullet_copy_has_no_artificial_maximum(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['bullets'][0] = (
            '📦【Ausführliche Produktangabe】Das Set enthält vier einzeln '
            'gestaltete Figuren mit klar erkennbaren Formen, stabilen Aufstellflächen und '
            'abgestimmten Details für Regale, Tische und saisonale Dekorationen. '
            'Jede Figur lässt sich separat platzieren, nach dem Umstellen erneut ausrichten '
            'und mit vorhandenen Dekorationen kombinieren, ohne dass eine feste Reihenfolge '
            'oder ein bestimmter Aufbau erforderlich ist.'
        )
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

    def test_listing_package_rejects_repeated_bullet_sentences(self):
        data = copy.deepcopy(self.listing_package())
        repeated = (
            'Die vier Figuren lassen sich einzeln auf Regalen, Tischen und Fensterbänken '
            'platzieren und nach dem Umstellen erneut ausrichten'
        )
        data['listings'][0]['bullets'][0] = (
            f'📦【Flexible Platzierung】{repeated}. {repeated}.'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('repeats the same sentence' in error
                            for error in result['errors']))

    def test_listing_package_rejects_thin_bullet_copy(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['bullets'][0] = (
            '📦【Klarer Lieferumfang】Die Variante enthält die angegebenen Teile. '
            'Der Inhalt lässt sich vorab überblicken.'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('more than 200 visible characters' in error
                            for error in result['errors']))

    def test_listing_package_accepts_two_to_four_core_keywords_and_optional_scene(self):
        data = copy.deepcopy(self.listing_package())
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        data['listings'][0]['title_keywords'] = ['Dekoration', 'Papierdekoration']
        data['listings'][0]['title_scene'] = ''
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        data = copy.deepcopy(self.listing_package())
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

        listing['title'] = ('12 Stück Dekoration, Dekoration aus Papier und Festschmuck '
                            'für Feiern')
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
        self.assertTrue(any('source_type must be own_product or same_product_evidence' in error
                            for error in result['errors']))
        self.assertTrue(any('five non-empty bullets' in error for error in result['errors']))
        self.assertTrue(any('uses non-confirmed fact' in error for error in result['errors']))
        self.assertTrue(any('contains an ASIN' in error for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
