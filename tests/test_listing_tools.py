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
    def primary_bullet_outline():
        excerpts = [
            'Eine Dekoration aus Papier',
            'Die Papierdekoration lässt sich auf geeigneten Flächen gezielt anordnen',
            'Die klare Form setzt einen sichtbaren dekorativen Akzent',
            'Die Gestaltung ist für bestätigte Feiern und saisonale Innenräume vorgesehen',
            'Sie kann einzeln stehen oder mit abgestimmten Elementen kombiniert werden',
        ]
        return [
            {
                'source_index': index,
                'source_topic': f'Reference topic {index}',
                'source_details': [f'Reference detail {index}'],
                'own_fact_ids': ['F1'],
                'description_excerpt': excerpts[index - 1],
            }
            for index in range(1, 6)
        ]

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
                                              'Innenraum, einzeln platzierbar oder mit '
                                              'Dekoration kombinierbar'),
                          'bullets': [
                              '📦【Dekoration für kleine Flächen】Die Dekorationselemente setzen auf Tisch, Regal oder Fensterbank einen klaren saisonalen Akzent. Jedes Element kann einzeln platziert oder zusammen mit vorhandener Festdekoration verwendet werden. So lässt sich der verfügbare Platz flexibel nutzen, ohne eine feste Anordnung vorauszusetzen.',
                              '🧩【Leichtes Papiermaterial】Die Dekoration besteht aus Papier und lässt sich unkompliziert an einem trockenen Platz im Innenraum aufstellen. Das leichte Material erleichtert das Umstellen zwischen Tisch, Regal und Fensterbank. Die klaren Formen bleiben dabei gut sichtbar und ergänzen unterschiedliche saisonale Dekorationsstile.',
                              '✨【Flexibel kombinierbar】Die einzelnen Elemente können als ruhiger Akzent verwendet oder mit bereits vorhandener Tisch- und Raumdekoration kombiniert werden. Sie lassen sich nebeneinander verteilen oder an verschiedenen Stellen des Raums platzieren. Dadurch kann die Dekoration an kleine und größere freie Flächen angepasst werden.',
                              '🎉【Für festliche Arrangements】Die Gestaltung eignet sich für Feiern und saisonale Innenraumdekorationen. Auf Esstisch, Kommode oder Regal ergänzt sie bestehende Arrangements, ohne einen bestimmten Aufbau zu verlangen. Nach dem Anlass lassen sich die leichten Elemente abnehmen und für den nächsten Einsatz an einem trockenen Ort aufbewahren.',
                              '💡【Einfach aufstellen und lagern】Die Papierdekoration wird auf einer trockenen, ebenen Fläche platziert und kann bei Bedarf an einen anderen Ort versetzt werden. Für die Aufbewahrung sollte sie vor Feuchtigkeit und starkem Druck geschützt liegen. So bleiben Form und bedruckte Oberfläche zwischen mehreren saisonalen Einsätzen erhalten.',
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
                          'claim_fact_ids': ['F1'],
                          'field_fact_ids': {
                              'title': ['F1'],
                              'item_highlights': ['F1'],
                              'bullet_1': ['F1'],
                              'bullet_2': ['F1'],
                              'bullet_3': ['F1'],
                              'bullet_4': ['F1'],
                              'bullet_5': ['F1'],
                              'description': ['F1'],
                          },
                          'translations': {
                              'title': '适用于庆典和节日的纸质装饰与派对装饰',
                              'item_highlights': ('纸质材质造型清晰，适合桌面、置物架和室内空间，'
                                                  '可单独摆放或与现有节日装饰搭配'),
                              'bullets': [
                                  '📦【适合小空间装饰】可摆放在桌面、置物架或窗台。',
                                  '🧩【轻巧纸质材质】适合干燥的室内位置。',
                                  '✨【灵活搭配】可单独使用或搭配现有节日装饰。',
                                  '🎉【适合节庆布置】适用于庆典和季节性室内装饰。',
                                  '💡【便于摆放收纳】请置于干燥平面并避免受潮挤压。',
                              ],
                              'description': ('纸质装饰适合节庆布置，可用于桌面、置物架和窗台。'
                                              '材质：纸；颜色：白色；尺寸：10厘米；包装：1件装饰。'),
                              'search_terms': '装饰品 挂饰 派对用品',
                          }}],
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

    def test_item_highlights_requires_a_title_core_keyword(self):
        data = self.listing_package()
        data['listings'][0]['item_highlights'] = (
            data['listings'][0]['item_highlights'].replace(
                'Dekoration kombinierbar', 'Festdeko kombinierbar'
            )
        )
        result = package_validator.validate(data)
        self.assertTrue(any(
            'item_highlights must include at least one title core keyword' in error
            for error in result['errors']
        ))

    def test_item_highlights_accepts_verified_title_keyword_alias(self):
        data = self.listing_package()
        data['listings'][0]['item_highlights'] = (
            data['listings'][0]['item_highlights'].replace(
                'Dekoration kombinierbar', 'Deko kombinierbar'
            )
        )
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

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
        listing['primary_reference_bullet_outline'] = self.primary_bullet_outline()
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

        original_terms = listing['search_terms']
        data['competitors'].append({
            'id': 'C2', 'marketplace': 'DE', 'product_group': 'P2',
            'status': 'complete', 'asin': 'B012345679',
            'title': 'Tischschmuck aus Papier für Feiern',
        })
        extra = {
            'marketplace': 'DE', 'variant_id': 'V1',
            'phrase': 'tischschmuck', 'source_asin': 'B012345679',
            'source_tool': 'same_category_title_terms', 'source_field': 'title',
            'source_marketplace': 'DE', 'organic_results_checked': 20,
            'relevant_results': 16, 'relevance_band': 'high',
            'decision': 'adopt', 'local_volume_claimed': False,
        }
        data['search_term_audits'].append(extra)
        listing['search_terms'] += ' tischschmuck'
        result = package_validator.validate(data)
        self.assertTrue(any('title_reference must cite every usable competitor title: B012345679'
                            in error for error in result['errors']))
        listing['title_reference'] += '；对比 B012345679 标题的产品词和场景词'
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        extra['source_asin'] = 'B012345699'
        self.assertTrue(any('title-term audit source_asin' in error for error in
                            package_validator.validate(data)['errors']))
        extra['source_asin'] = 'B012345679'
        extra['source_field'] = 'bullet_1'
        self.assertTrue(any('must use source_field=title' in error for error in
                            package_validator.validate(data)['errors']))
        data['search_term_audits'].pop()
        data['competitors'].pop()
        listing['search_terms'] = original_terms

        data['search_term_audits'] = data['search_term_audits'][:1]
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('requires synonym candidates from reference listing titles' in error
                            for error in result['errors']))

    def test_listing_package_rejects_internal_variant_codes_in_buyer_copy(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['item_highlights'] = (
            'Design A: Papiermaterial mit klarer Form für Tisch, Regal und Innenraum, '
            'einzeln platzierbar oder mit Dekoration kombinierbar'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('contains internal variant codes' in error
                            for error in result['errors']))

        data['listings'][0]['buyer_visible_variant_terms'] = ['Design A']
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

    def test_buyer_copy_rejects_internal_confirmation_and_reference_language(self):
        errors = []
        package_validator.validate_buyer_copy(
            errors,
            'FR',
            'V1',
            [
                ('bullet 1', '【Contenu confirmé】Le kit contient des fils et des aiguilles.'),
                ('bullet 2', ('Les dimensions indiquées concernent l’emballage. '
                              'La pochette du produit de référence ne fait pas partie du kit.')),
            ],
        )
        self.assertEqual(
            sum('contains internal confirmation' in error for error in errors), 2
        )

    def test_listing_package_rejects_internal_process_language_in_chinese_translation(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['translations']['bullets'][0] = (
            '📦【已确认的套装内容】包装资料记录了尺寸；自有套装不包含竞品图中的收纳包。'
        )
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('Chinese translation bullet 1 contains internal' in error
                            for error in result['errors']))

    def test_listing_package_requires_complete_chinese_translations(self):
        data = copy.deepcopy(self.listing_package())
        del data['listings'][0]['translations']
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('translations must be an object' in error
                            for error in result['errors']))

    def test_primary_reference_requires_five_ordered_bullet_topics_and_confirmed_facts(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['primary_reference_asin'] = 'B012345678'
        errors = []
        fact_by_id = {fact['id']: fact for fact in data['facts']}
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertTrue(any('must contain five ordered source topics' in error
                            for error in errors))

        listing['primary_reference_bullet_outline'] = self.primary_bullet_outline()
        listing['bullet_references'] = [f'参考 B012345678 第{i}点' for i in range(1, 6)]
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertEqual(errors, [])

        del listing['primary_reference_bullet_outline'][0]['source_details']
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertTrue(any('requires non-empty source_details' in error
                            for error in errors))
        listing['primary_reference_bullet_outline'] = self.primary_bullet_outline()

        data['facts'][0]['status'] = 'unconfirmed'
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, {data['facts'][0]['id']: data['facts'][0]}
        )
        self.assertTrue(any('uses non-confirmed fact F1' in error for error in errors))

    def test_primary_reference_bullets_must_map_into_html_description(self):
        data = self.listing_package()
        listing = data['listings'][0]
        listing['primary_reference_asin'] = 'B012345678'
        listing['primary_reference_bullet_outline'] = self.primary_bullet_outline()
        listing['bullet_references'] = [f'参考 B012345678 第{i}点' for i in range(1, 6)]
        fact_by_id = {fact['id']: fact for fact in data['facts']}

        listing['primary_reference_bullet_outline'][2]['description_excerpt'] = ''
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertTrue(any('requires a substantive description_excerpt' in error
                            for error in errors))

        listing['primary_reference_bullet_outline'][2]['description_excerpt'] = (
            'Eine neue unbelegte Eigenschaft'
        )
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertTrue(any('description_excerpt is absent from HTML description' in error
                            for error in errors))

        listing['primary_reference_bullet_outline'][2]['description_excerpt'] = (
            'Die klare Form setzt einen sichtbaren dekorativen Akzent'
        )
        listing['field_fact_ids']['description'] = []
        errors = []
        package_validator.validate_primary_bullet_outline(
            errors, 'DE', 'V1', listing, fact_by_id
        )
        self.assertTrue(any('own_fact_ids must be included in field_fact_ids.description'
                            in error for error in errors))

    def test_fitment_products_require_confirmed_compatibility_in_front_end_copy(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['compatibility_required'] = True
        listing['primary_compatibility_term'] = 'PAULTRA2'
        listing['compatibility_terms'] = [
            'PAULTRA2', 'PureAir Ultra 2', '242047805', '5303918847', 'EAP12364179'
        ]
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title must contain primary compatibility term' in error
                            for error in result['errors']))
        self.assertTrue(any('omit confirmed compatibility terms' in error
                            for error in result['errors']))

    def test_compatibility_validator_accepts_models_and_part_numbers_in_both_languages(self):
        listing = {
            'compatibility_required': True,
            'primary_compatibility_term': 'PAULTRA2',
            'compatibility_terms': [
                'PAULTRA2', 'PureAir Ultra 2', '242047805', '5303918847', 'EAP12364179'
            ],
            'translations': {
                'title': '6个装PAULTRA2冰箱空气过滤器替换滤芯，95 × 45 × 9毫米',
                'item_highlights': ('兼容PureAir Ultra 2，以及242047805、5303918847、'
                                    'EAP12364179替换件号'),
                'bullets': [
                    '🔧【兼容PAULTRA2】适用于PAULTRA2冰箱空气过滤系统。',
                    '📦【6个装】提供多个替换滤芯。',
                    '🌿【过滤异味】帮助过滤冰箱空气。',
                    '🛠️【便于安装】可装入对应滤芯仓。',
                    '✅【日常替换】适合定期维护。',
                ],
                'description': ('兼容PAULTRA2、PureAir Ultra 2、242047805、'
                                '5303918847和EAP12364179。'),
            },
        }
        errors = []
        package_validator.validate_compatibility_copy(
            errors,
            'FR',
            'V1',
            listing,
            '6 filtres à air PAULTRA2 de rechange pour réfrigérateur, 95 x 45 x 9 mm',
            ('Compatibles Frigidaire PureAir Ultra 2 et Electrolux 242047805, '
             '5303918847, EAP12364179 ; lot de 6'),
            [
                '🔧【Compatibilité PAULTRA2】Compatible avec le système PAULTRA2.',
                '📦【Lot de 6】Six filtres de rechange.',
                '🌿【Filtration】Aide à filtrer l’air du réfrigérateur.',
                '🛠️【Installation】S’insère dans le logement compatible.',
                '✅【Entretien】Convient au remplacement régulier.',
            ],
            ('Compatible PAULTRA2, PureAir Ultra 2, 242047805, 5303918847 '
             'et EAP12364179.'),
        )
        self.assertEqual(errors, [])

        listing['translations']['item_highlights'] = '请核对原滤芯尺寸和冰箱说明书。'
        package_validator.validate_compatibility_copy(
            errors,
            'FR',
            'V1',
            listing,
            '6 filtres à air PAULTRA2 de rechange pour réfrigérateur, 95 x 45 x 9 mm',
            ('Compatibles Frigidaire PureAir Ultra 2 et Electrolux 242047805, '
             '5303918847, EAP12364179 ; lot de 6'),
            [
                '🔧【Compatibilité PAULTRA2】Compatible avec le système PAULTRA2.',
                '📦【Lot de 6】Six filtres de rechange.',
                '🌿【Filtration】Aide à filtrer l’air du réfrigérateur.',
                '🛠️【Installation】S’insère dans le logement compatible.',
                '✅【Entretien】Convient au remplacement régulier.',
            ],
            ('Compatible PAULTRA2, PureAir Ultra 2, 242047805, 5303918847 '
             'et EAP12364179.'),
        )
        self.assertTrue(any('Chinese title and item_highlights omit confirmed' in error
                            for error in errors))

    def test_listing_package_requires_field_level_fact_assignments(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        del listing['field_fact_ids']['description']
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('field_fact_ids.description must contain' in error
                            for error in result['errors']))

        listing['field_fact_ids']['description'] = ['F2']
        result = package_validator.validate(data)
        self.assertTrue(any('references unknown fact F2' in error
                            for error in result['errors']))

    def test_fitment_copy_requires_primary_term_in_bullet_and_full_list_in_description(self):
        listing = {
            'compatibility_required': True,
            'primary_compatibility_term': 'PAULTRA2',
            'compatibility_terms': ['PAULTRA2', 'PureAir Ultra 2', '242047805'],
            'translations': {
                'title': 'PAULTRA2冰箱空气过滤器',
                'item_highlights': '兼容PureAir Ultra 2和242047805',
                'bullets': ['🔧【尺寸】单个尺寸95 × 45 × 9毫米。'],
                'description': '兼容PAULTRA2和PureAir Ultra 2。',
            },
        }
        errors = []
        package_validator.validate_compatibility_copy(
            errors, 'FR', 'V1', listing,
            'Filtre à air PAULTRA2 pour réfrigérateur',
            'Compatible PureAir Ultra 2 et 242047805',
            ['🔧【Dimensions】Chaque filtre mesure 95 x 45 x 9 mm.'],
            'Compatible PAULTRA2 et PureAir Ultra 2.',
        )
        self.assertTrue(any('bullet 1 must lead with primary compatibility term' in error
                            for error in errors))
        self.assertTrue(any('description omits confirmed compatibility terms: 242047805'
                            in error for error in errors))
        self.assertTrue(any('Chinese bullet 1 must contain primary compatibility term'
                            in error for error in errors))
        self.assertTrue(any('Chinese description omits confirmed compatibility terms'
                            in error for error in errors))

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
            'primary_reference_bullet_outline': self.primary_bullet_outline(),
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

    def test_listing_package_requires_three_core_keywords_and_optional_scene(self):
        data = copy.deepcopy(self.listing_package())
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        data['listings'][0]['title_keywords'] = ['Dekoration', 'Papierdekoration']
        result = package_validator.validate(data)
        self.assertTrue(any('title_keywords must contain exactly 3 distinct phrases' in error
                            for error in result['errors']))
        data['listings'][0]['title_keywords'] = ['Dekoration', 'Papierdekoration', 'Festschmuck', 'Feierdeko']
        result = package_validator.validate(data)
        self.assertTrue(any('title_keywords must contain exactly 3 distinct phrases' in error
                            for error in result['errors']))
        data = copy.deepcopy(self.listing_package())
        data['keywords'][2]['is_core'] = False
        data['listings'][0]['title_scene'] = 'für Hochzeiten'
        result = package_validator.validate(data)
        self.assertFalse(result['ready_for_delivery'])
        self.assertTrue(any('title keyword is not marked as core: Festschmuck' in error
                            for error in result['errors']))
        self.assertTrue(any('title does not contain title_scene: für Hochzeiten' in error
                            for error in result['errors']))

    def test_short_title_is_valid_without_size_padding(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['title'] = 'Dekoration, Papierdekoration und Festschmuck für Feiern'
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])

    def test_item_highlights_below_target_is_editorial_warning(self):
        data = copy.deepcopy(self.listing_package())
        data['listings'][0]['item_highlights'] = (
            'Dekoration aus Papier für Tisch und Regal mit klarer Form und '
            'flexibler Platzierung bei saisonalen Feiern'
        )
        result = package_validator.validate(data)
        self.assertTrue(result['ready_for_delivery'])
        self.assertTrue(any('120-125 editorial target' in warning
                            for warning in result['warnings']))

    def test_title_size_requires_purchase_reason_and_final_position(self):
        data = copy.deepcopy(self.listing_package())
        listing = data['listings'][0]
        listing['title_scene'] = ''
        listing['title'] = 'Dekoration, Papierdekoration und Festschmuck, 33 x 183 cm'
        result = package_validator.validate(data)
        self.assertTrue(any('title_size_term must match' in error for error in result['errors']))
        self.assertTrue(any('title_size_reason must explain' in error for error in result['errors']))
        listing['title_size_term'] = '33 x 183 cm'
        listing['title_size_reason'] = 'Required for the confirmed table fit'
        self.assertTrue(package_validator.validate(data)['ready_for_delivery'])
        listing['title'] = '33 x 183 cm Dekoration, Papierdekoration und Festschmuck'
        result = package_validator.validate(data)
        self.assertTrue(any('title size must appear at the end' in error for error in result['errors']))
        listing['title'] = 'Dekoration 10 cm, Papierdekoration und Festschmuck, 33 x 183 cm'
        result = package_validator.validate(data)
        self.assertTrue(any('title may contain at most one size group' in error
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
