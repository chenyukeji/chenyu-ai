#!/usr/bin/env python3
"""Offline verification of fixed-layout invoice generation. Contains no real buyer data."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import json
import tempfile
import contextlib
import io
import re
import unittest
import pymupdf as fitz

PATH = Path(__file__).with_name('generate_invoice.py')
spec=spec_from_file_location('generate_invoice',PATH)
mod=module_from_spec(spec)
spec.loader.exec_module(mod)
SAMPLE=json.loads((PATH.parent.parent/'assets/order.example.json').read_text(encoding='utf-8'))

class InvoiceTests(unittest.TestCase):
    def pln_example(self):
        data = deepcopy(SAMPLE)
        data.update(currency='PLN', sales_channel='Amazon.pl',
                    seller_template='imported', seller_confirmed=True, order_total='24.60')
        data['seller'] = {'company':'exampletradingcompany', 'sales_name':'Example shop',
                          'address_lines':['CN', 'example street 10', 'example building 2',
                                           'example city, Example province', '000000'],
                          'tel':'+0000000000', 'email':'seller@example.test', 'vat_number':'SELLER-TEST'}
        data['items'][0].update(title='Zestaw ozdób, żółty', description='Ozdoby żółte',
                                unit_price='24.60', line_total='24.60')
        data['buyer']['country'] = 'Poland'
        data['billing_request'] = {'order_id':data['order_id'], 'buyer':{
            'name':'FIRMA PRZYKŁAD', 'address_lines':['Przykładowa 21'], 'city':'Łódź',
            'postal_code':'00-000', 'country':'Poland', 'vat_number':'PL1111111111'}}
        return data

    def test_billing_request_takes_priority_without_merging_shipping_fields(self):
        data = self.pln_example()
        original = deepcopy(data)
        normalized = mod.normalize(data)
        self.assertEqual(data, original)
        self.assertEqual(normalized['buyer'], data['billing_request']['buyer'])
        self.assertEqual(normalized['shipping_buyer'], data['buyer'])
        self.assertEqual(normalized['buyer_source'], 'buyer_invoice_message')
        text = self.render_text(data)[0]
        for value in ('FIRMA PRZYKŁAD', 'Przykładowa 21', 'Łódź', 'PL1111111111',
                      'SELLER-TEST', 'Zestaw ozdób, żółty', 'Ozdoby żółte'):
            self.assertIn(value, text)
        for value in ('Camille EXEMPLE', 'Lyon', 'France', '€', 'EUR', 'JiuYue_KeJi',
                      mod.SOURCE_SELLER_COMPANY, '+8617371452467', 'pinghujiedao'):
            self.assertNotIn(value, text)
        self.assertEqual(normalized['tax']['amount'], Decimal('4.60'))
        self.assertIn('VAT (23%):', text)
        self.assertIn('4,60', text)
        self.assertEqual(text.count('PLN'), 5)

    def test_imported_seller_restores_address_label_on_every_page(self):
        for currency, channel in [('EUR', 'Amazon.de'), ('PLN', 'Amazon.pl')]:
            data = self.pln_example()
            data.update(currency=currency, sales_channel=channel, order_total='49.20')
            data['items'] *= 2
            with self.subTest(currency=currency), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'invoice.pdf'
                mod.invoice_pdf(mod.normalize(data), path)
                with fitz.open(path) as document:
                    self.assertEqual(len(document), 1)
                    for page in document:
                        header = ' '.join(page.get_text(clip=fitz.Rect(10, 108, 580, 158)).split())
                        expected = 'ADD: ' + ', '.join(data['seller']['address_lines'])
                        self.assertEqual(header, expected)
                        self.assertEqual(page.get_text().count('ADD:'), 1)
                        self.assertNotIn('pinghujiedao', page.get_text())
                        detail = page.get_text(clip=fitz.Rect(384, 295, 560, 378))
                        self.assertNotIn('ADD:', detail)

    def test_two_distinct_products_share_original_columns_without_shrinking(self):
        data = self.pln_example()
        first = deepcopy(data['items'][0])
        second = dict(first, title='Drugi produkt', description='Drugi opis')
        data['items'] = [first, second]
        data['order_total'] = '49.20'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invoice.pdf'
            mod.invoice_pdf(mod.normalize(data), path)
            with fitz.open(path) as doc:
                self.assertEqual(len(doc), 1)
                page = doc[0]
                text = page.get_text()
                for value in (first['title'], second['title'], 'Total Amount:', 'Amount excl. VAT:', 'VAT (23%):', '49,20', '40,00', '9,20'):
                    self.assertIn(value, text)
                for title, top, bottom in ((first['title'], mod.ROW_TOP, mod.ROW_BOTTOM),
                        (second['title'], mod.ROW_BOTTOM, mod.ROW_BOTTOM*2-mod.ROW_TOP)):
                    boxes = page.search_for(title)
                    self.assertEqual(len(boxes), 1)
                    self.assertGreaterEqual(boxes[0].y0, top)
                    self.assertLessEqual(boxes[0].y1, bottom)
                vat = page.search_for('VAT (23%):')[0]
                self.assertGreater(vat.y0, mod.ROW_BOTTOM*2-mod.ROW_TOP)
                self.assertLess(vat.y1, page.rect.height-30)
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines', []):
                        for span in line['spans']:
                            self.assertLessEqual(span['bbox'][3], page.rect.height)
                self.assertEqual(text.count('COMMERCIAL INVOICE'), 1)
                self.assertNotIn('Page 1/2', text)

    def test_incomplete_or_other_order_billing_message_never_falls_back(self):
        data = self.pln_example()
        data['billing_request']['order_id'] = '403-9999999-9999999'
        with self.assertRaisesRegex(ValueError, 'same order_id'):
            mod.normalize(data)
        for field in ('name', 'city', 'postal_code', 'country', 'address_lines'):
            data = self.pln_example()
            del data['billing_request']['buyer'][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'billing_request.buyer'):
                mod.normalize(data)

    def test_conflicting_currency_and_unverified_seller_are_rejected(self):
        for field, value in [('template_currency','EUR'),
                             ('seller_confirmed',False), ('seller_confirmed','true'), ('currency',None)]:
            data = self.pln_example()
            data[field] = value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                mod.normalize(data)
        data = self.pln_example()
        data['seller'] = {}
        with self.assertRaisesRegex(ValueError, 'seller.company'):
            mod.normalize(data)

    def test_pln_template_preserves_all_original_graphics_on_each_page(self):
        data = self.pln_example()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'invoice.pdf'
            mod.invoice_pdf(mod.normalize(data), path)
            with fitz.open(mod.TEMPLATE) as source, fitz.open(path) as document:
                graphical_keys = ('items','type','rect','color','fill','width','fill_opacity','stroke_opacity')
                expected = [{key:entry.get(key) for key in graphical_keys} for entry in source[0].get_drawings()]
                for page in document:
                    self.assertEqual(page.rect, source[0].rect)
                    self.assertEqual([{key:entry.get(key) for key in graphical_keys} for entry in page.get_drawings()], expected)
                    self.assertIn('exampletradingcompany',page.get_text())
                    self.assertNotIn('€',page.get_text())
                    self.assertIn('Buyer VAT/NIP: PL1111111111',page.get_text())
                    spans = [span for block in page.get_text('dict')['blocks'] for line in block.get('lines',[]) for span in line['spans']]
                    for span in spans:
                        self.assertGreaterEqual(span['bbox'][0], 0)
                        self.assertLessEqual(span['bbox'][2], page.rect.width)
                text = document[-1].get_text()
                self.assertIn('24,60', text)
                self.assertIn('4,60', text)

    def test_known_sellers_can_use_confirmed_pln_without_importing_identity(self):
        for template in ('jiuyue', 'renhaoyuan'):
            data = self.pln_example()
            data['seller_template'] = template
            data['seller'] = {}
            text = self.render_text(data)[0]
            self.assertIn(mod.SELLER_PROFILES[template]['company'], text)
            self.assertNotIn('€', text)
            self.assertIn('PLN', text)

    def test_text_parser_reads_pln_amounts_and_rejects_mixed_currencies(self):
        raw = '''403-1234567-7654321
销售渠道: Amazon.pl
购买日期: 2026年10月1日
| [Example Item](https://www.amazon.pl/gp/product/B000000000) | 数量: 1 | 商品小计: 24,60 zł | 运费总额: PLN 1.00 | 促销: -1.00 zł | 商品总计: 24,60 zł |'''
        parsed = mod.extract_order_text(raw)
        self.assertEqual(parsed['currency'], 'PLN')
        self.assertEqual(parsed['order_total'], '24.60')
        self.assertEqual(parsed['shipping_fee'], '1.00')
        self.assertEqual(parsed['shipping_discount'], '1.00')
        parsed['buyer'] = {'country': 'Poland'}
        self.assertEqual(mod.normalize(parsed)['currency'], 'PLN')
        with self.assertRaisesRegex(ValueError, 'Conflicting currencies'):
            mod.extract_order_text(raw.replace('PLN 1.00', '€1.00'))
        with self.assertRaisesRegex(ValueError, 'structured JSON billing_request'):
            mod.extract_order_text(raw+'\nDane do faktury: example company')
        with self.assertRaisesRegex(ValueError, 'Conflicting order IDs'):
            mod.extract_order_text(raw+'\n403-9999999-9999999')

    def test_unicode_is_preserved_or_rejected_never_silently_dropped(self):
        data = self.pln_example()
        data['billing_request']['buyer']['name'] = 'Żółć Śląsk Łódź'
        self.assertIn('Żółć Śląsk Łódź',self.render_text(data)[0])
        data['billing_request']['buyer']['name'] = 'Unsupported \U0001f600'
        with self.assertRaisesRegex(ValueError, 'Unsupported glyph'):
            self.render_text(data)

    def test_original_pln_is_default_without_additional_confirmation(self):
        for legacy in ({}, {'template_currency':None}, {'template_currency':'PLN'}):
            data = self.pln_example()
            data.update(legacy)
            normalized = mod.normalize(data)
            self.assertEqual(normalized['currency'], 'PLN')
            self.assertEqual(normalized['items'][0]['unit_price'], Decimal('24.60'))
            self.assertEqual(normalized['order_total'], Decimal('24.60'))
            text = self.render_text(data)[0]
            self.assertIn('PLN', text)
            self.assertNotIn('€', text)
            self.assertIn('24,60', text)
        data = deepcopy(SAMPLE)
        data['template_currency'] = 'PLN'
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            mod.normalize(data)

    def test_displayed_item_total_supplies_default_invoice_amount(self):
        for subtotal_label, total_label in [('Item subtotal','Item total'), ('商品小计','商品总计')]:
            raw = f'''403-1234567-7654321
销售渠道: Amazon.fr
购买日期: 2026年10月1日
| [Example Item](https://www.amazon.fr/gp/product/B000000000) | 数量: 1 |
Unit price (VAT exclusive): €7.49
{subtotal_label}: €8.99
{total_label}: €8.99
Sales proceeds: €6.50'''
            parsed = mod.extract_order_text(raw)
            self.assertEqual(parsed['order_total'], '8.99')
            self.assertEqual(parsed['amount_source'], 'displayed_item_total')
            self.assertEqual(parsed['currency'], 'EUR')
            parsed['buyer'] = deepcopy(SAMPLE['buyer'])
            normalized = mod.normalize(parsed)
            self.assertEqual(normalized['order_total'], Decimal('8.99'))
            self.assertEqual(normalized['tax']['basis'], 'order_total')
            self.assertFalse(any('grand total' in warning.lower() for warning in normalized['warnings']))
            text = self.render_text(parsed)[0]
            self.assertIn('8,99', text)
            self.assertEqual(normalized['items'][0]['unit_price'], Decimal('8.99'))
            self.assertEqual(normalized['net_amount'], Decimal('7.49'))
            self.assertNotIn('6,50', text)

    def render_text(self,payload):
        norm=mod.normalize(payload)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'invoice.pdf'
            mod.invoice_pdf(norm,path)
            self.assertGreater(path.stat().st_size,15000)
            with fitz.open(path) as doc:
                return [page.get_text() for page in doc]

    def test_filename_is_always_exact_order_number(self):
        order_id = SAMPLE['order_id']
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            self.assertEqual(mod.resolve_output_file(order_id, folder), folder / f'{order_id}.pdf')
            with self.assertRaisesRegex(ValueError, 'must be a directory'):
                mod.resolve_output_file(order_id, folder / 'invoice.pdf')

    def test_cli_writes_invoice_named_with_order_number(self):
        order_id = SAMPLE['order_id']
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            input_file = folder / 'example.json'
            input_file.write_text(json.dumps(SAMPLE), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                mod.main(['--input', str(input_file), '--invoice-date', '2026-10-01',
                          '--output', str(folder)])
            files = list(folder.glob('*.pdf'))
            self.assertEqual([p.name for p in files], [f'{order_id}.pdf'])
            with fitz.open(files[0]) as pdf:
                self.assertIn('COMMERCIAL INVOICE', pdf[0].get_text())

    def test_date_comes_from_order_purchase_not_generation_date(self):
        data=deepcopy(SAMPLE)
        data['purchase_date']='2026-10-07'
        norm=mod.normalize(data)
        self.assertEqual(norm['purchase_date'],'2026-10-07')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'sample.pdf'
            mod.invoice_pdf(norm,path)
            with fitz.open(path) as doc:
                self.assertIn('07/10/2026',doc[0].get_text())
                self.assertNotIn('08/10/2026',doc[0].get_text())

    def test_legacy_invoice_date_is_rejected(self):
        data=deepcopy(SAMPLE)
        data['invoice_date']='2026-10-08'
        with self.assertRaisesRegex(ValueError,'invoice_date is unsupported'):
            mod.normalize(data)

    def test_missing_purchase_date_blocks_invoice(self):
        data=deepcopy(SAMPLE)
        data.pop('purchase_date')
        with self.assertRaisesRegex(ValueError,'purchase_date is required'):
            mod.normalize(data)

    def test_explicit_invoice_date_must_match_purchase_date(self):
        with self.assertRaisesRegex(ValueError,'must match purchase_date'):
            mod.normalize(SAMPLE,invoice_date='2026-10-08')

    def test_order_date_text_parser(self):
        raw='''| [403-1234567-7654321](https://example.test/order) | [Boa en Plumes Blanc](https://www.amazon.fr/gp/product/B000000000) | 数量: 1 | 商品小计: €7.99 |
购买日期: | 2026年10月1日周四 15:01 MEST
配送地址
| Camille EXEMPLE<br>10 Rue Exemple<br>Lyon, 69000<br>法国 |'''
        self.assertEqual(mod.extract_order_text(raw)['purchase_date'],'2026-10-01')

    def test_pdf_preserves_reference_headings_and_layout(self):
        data=deepcopy(SAMPLE)
        text=self.render_text(data)[0]
        self.assertIn('COMMERCIAL INVOICE',text)
        self.assertIn('Paypal package',text)
        self.assertIn('Importer/Buyer/Receiver:',text)
        self.assertIn('Manufacturer/Seller/Shipper:',text)
        self.assertIn('Description',text)
        self.assertIn('Boa en plumes\nblanc, 1,8 m',text)
        self.assertIn('VAT (20%):',text)
        self.assertIn('1,33',text)
        self.assertIn('Total Amount:',text)
        self.assertIn('403-1234',text)  # original Item No. is order ID, not SKU
        self.assertNotIn('EXAMPLE-WHITE-BOA',text)
        self.assertNotIn('Amazon FBA',text)
        self.assertNotIn('373,66',text)

    def test_recipient_in_buyer_heading_and_address_has_no_name(self):
        data=deepcopy(SAMPLE)
        data['buyer']['legal_company_name']='Legal label must not be printed'
        d=mod.normalize(data)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'invoice.pdf'
            mod.invoice_pdf(d,path)
            with fitz.open(path) as doc:
                page=doc[0]
                blocks=page.get_text('dict')['blocks']
                spans=[span for blk in blocks for line in blk.get('lines',[]) for span in line['spans']]
                content=page.get_text()
                self.assertIn('Contact:',content)
                self.assertIn('Company Name:',content)
                self.assertIn('Camille EXEMPLE',content)
                self.assertNotIn('Société Exemple',content)
                self.assertNotIn('Legal label must not be printed',content)
                names=[t for t in spans if t['text']=='Camille EXEMPLE']
                self.assertEqual(len(names),1)
                self.assertAlmostEqual(names[0]['origin'][1],256.2,delta=0.2)
                street=next(t for t in spans if t['text']=='10 Rue Exemple')
                building=next(t for t in spans if t['text']=='Bâtiment A')
                city=next(t for t in spans if t['text']=='Lyon')
                self.assertLess(names[0]['origin'][1],street['origin'][1])
                self.assertLess(street['origin'][1],building['origin'][1])
                self.assertLess(building['bbox'][3],city['bbox'][1])

    def test_address_can_exclude_duplicate_recipient(self):
        data=deepcopy(SAMPLE)
        data['buyer']['address_lines'].insert(0,'Camille EXEMPLE')
        content=self.render_text(data)[0]
        self.assertEqual(content.count('Camille EXEMPLE'),1)

    def test_address_cannot_overflow_three_lines(self):
        data=deepcopy(SAMPLE)
        data['buyer']['address_lines']=['Street 1','Building 2','Apartment 3','Other 4']
        with self.assertRaisesRegex(ValueError,'exceeds 3 printed lines'):
            self.render_text(data)

    def test_buyer_name_required(self):
        data=deepcopy(SAMPLE)
        data['buyer']['name']=''
        with self.assertRaisesRegex(ValueError,'buyer.name required'):
            self.render_text(data)

    def test_fixed_columns_match_reference(self):
        with fitz.open(mod.TEMPLATE) as doc:
            page=doc[0]
            assert page.rect.width > 595
            drawings=page.get_drawings()
            for x in [9.9,65.3,122.3,288.8,381.9,460.55,507.05,558.9]:
                self.assertTrue(any(abs(z['rect'].x0-x)<0.1 or abs(z['rect'].x1-x)<0.1
                                    for z in drawings),f'missing original border x={x}')
            txt=page.get_text()
            self.assertNotIn('373,66',txt)
            self.assertIsNone(re.search(r'\b\d{3}-\d{7}-\d{7}\b', txt))
            self.assertNotIn(SAMPLE['buyer']['name'], txt)

    def test_shipping_way_always_paypal_package(self):
        data=deepcopy(SAMPLE)
        data['fulfillment']='Amazon FBA'
        data['shipping_way']='Express'
        d=mod.normalize(data)
        self.assertEqual(d['shipping_way'],'Paypal package')
        txt=self.render_text(data)[0]
        self.assertIn('Paypal package',txt)
        self.assertNotIn('Express',txt)
        self.assertNotIn('Amazon FBA',txt)

    def test_destination_rates_and_pdf_labels(self):
        cases = [('UK', 'Amazon.co.uk', '20', '20.00'),
                 ('DE', 'Amazon.de', '19', '19.00'),
                 ('FR', 'Amazon.fr', '20', '20.00'),
                 ('IT', 'Amazon.it', '22', '22.00'),
                 ('ES', 'Amazon.es', '21', '21.00'),
                 ('NL', 'Amazon.nl', '21', '21.00'),
                 ('PL', 'Amazon.pl', '23', '23.00'),
                 ('CZ', '', '21', '21.00'),
                 ('AT', '', '20', '20.00'),
                 ('BE', 'Amazon.com.be', '21', '21.00')]
        for seller in ['jiuyue', 'renhaoyuan']:
            for code, channel, percent, expected in cases:
                with self.subTest(seller=seller, code=code), tempfile.TemporaryDirectory() as td:
                    data=deepcopy(SAMPLE)
                    data.update(seller_template=seller, sales_channel=channel, marketplace_code=code)
                    data['buyer']['country'] = mod.COUNTRY_NAMES[code][0]
                    # A gross price of 100 + rate yields exactly rate in VAT.
                    gross=str(Decimal('100')+Decimal(percent))
                    data['items'][0].update(unit_price=gross, line_total=gross)
                    data['order_total']=gross
                    n=mod.normalize(data)
                    self.assertEqual(n['tax']['amount'],Decimal(expected))
                    self.assertEqual(n['marketplace_code'],code)
                    pdf=Path(td)/'invoice.pdf'
                    mod.invoice_pdf(n,pdf)
                    with fitz.open(pdf) as doc:
                        page=doc[0]
                        text=page.get_text()
                        label=f'VAT ({percent}%):'
                        self.assertIn(label,text)
                        self.assertEqual(text.count('VAT ('),1)
                        if percent!='20':
                            self.assertNotIn('VAT (20%):',text)
                        spans=[sp for block in page.get_text('dict')['blocks']
                               for line in block.get('lines',[]) for sp in line['spans']]
                        lab=next(sp for sp in spans if sp['text']==label)
                        amount=next(sp for sp in spans if sp['text']=='€ '+expected.replace('.',','))
                        self.assertLess(abs(lab['origin'][1]-amount['origin'][1]),0.2)
                        self.assertLessEqual(lab['bbox'][2],amount['bbox'][0])
                        self.assertIn('Amount excl. VAT:', text)
                        self.assertEqual(n['net_amount'], Decimal('100.00'))
                        self.assertAlmostEqual(page.rect.width,595.3,places=1)

    def test_sales_channel_is_not_delivery_country(self):
        data=deepcopy(SAMPLE)
        data['buyer']['country']='Belgium'
        self.assertEqual(mod.normalize(data)['tax']['rate'],'0.21')
        data['sales_channel']='Amazon.com.be'
        self.assertEqual(mod.normalize(data)['tax']['rate'],'0.21')
        data['sales_channel']='https://www.AMAZON.DE/'
        self.assertEqual(mod.normalize(data)['tax']['rate'],'0.21')

    def test_missing_unknown_and_conflicting_sites_fail(self):
        for channel, code in [('', ''), ('Amazon.com', ''), ('Amazon.de.example.test', ''),
                              ('Amazon.de', 'FR'), ('', 'XX'), ('Amazon.com', 'FR')]:
            data=deepcopy(SAMPLE)
            data.update(sales_channel=channel,marketplace_code=code)
            with self.subTest(channel=channel, code=code),self.assertRaises(ValueError):
                mod.normalize(data)

    def test_supplied_rate_and_amount_must_match_destination(self):
        for tax in [{'rate':'0.20'}, {'rate':'NaN'}, {'rate':'19%'}, {'amount':'1.33'}]:
            data=deepcopy(SAMPLE)
            data.update(sales_channel='Amazon.de', tax=tax)
            data['buyer']['country'] = 'Germany'
            with self.subTest(tax=tax), self.assertRaises(ValueError):
                mod.normalize(data)
        data['tax']={'rate':'0.19','amount':'1.28'}
        self.assertEqual(mod.normalize(data)['tax']['amount'],Decimal('1.28'))

    def test_dynamic_rate_uses_total_and_rounds_to_cents(self):
        data=deepcopy(SAMPLE)
        data.update(sales_channel='Amazon.it',shipping_fee='1.00',order_total='8.99')
        data['buyer']['country'] = 'Italy'
        n=mod.normalize(data)
        self.assertEqual(n['tax']['amount'],Decimal('1.62'))
        self.assertEqual(n['tax']['basis'],'order_total')
        self.assertEqual(n['tax']['calculation'],'Price / 1.22 * 0.22')

    def test_pound_order_text_cannot_be_printed_as_euro(self):
        raw="""403-1234567-7654321
销售渠道: Amazon.co.uk
购买日期: 2026年10月1日
| [Example Item](https://www.amazon.co.uk/gp/product/B000000000) | 数量: 1 | 商品小计: £7.99 |"""
        parsed=mod.extract_order_text(raw)
        self.assertEqual(parsed['currency'],'GBP')
        with self.assertRaisesRegex(ValueError,'fixed EUR'):
            mod.normalize(parsed)

    def test_dynamic_rate_on_each_item_page(self):
        data=deepcopy(SAMPLE)
        data['sales_channel']='Amazon.de'
        data['buyer']['country']='Germany'
        data['items']*=2
        pages=self.render_text(data)
        for page in pages:
            self.assertIn('VAT (19%):',page)
            self.assertNotIn('VAT (20%):',page)
        self.assertIn('2,55',pages[-1])

    def test_parser_reads_sales_channel_not_product_link(self):
        raw="""403-1234567-7654321
销售渠道： Amazon.de
购买日期: 2026年10月1日
| [Article Exemple](https://www.amazon.fr/gp/product/B000000000) | 数量: 1 | 商品小计: €7.99 |"""
        parsed=mod.extract_order_text(raw)
        parsed['buyer'] = {'country': 'France'}
        self.assertEqual(mod.normalize(parsed)['tax']['rate'],'0.20')
        with self.assertRaisesRegex(ValueError,'Conflicting sales channels'):
            mod.extract_order_text(raw+'\n销售渠道: Amazon.fr')

    def test_fixed_vat_7_99(self):
        n=mod.normalize(SAMPLE)
        self.assertEqual(n['tax']['amount'],Decimal('1.33'))
        self.assertEqual(n['tax']['basis'],'items_subtotal')
        self.assertEqual(n['tax']['calculation'],'Price / 1.2 * 0.2')

    def test_vat_label_euro_and_amount_share_baseline(self):
        """Regression: € 1,33 must be one aligned line, not dropped below VAT label."""
        norm=mod.normalize(SAMPLE)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'invoice.pdf'
            mod.invoice_pdf(norm,path)
            with fitz.open(path) as doc:
                spans=[s for b in doc[0].get_text('dict')['blocks']
                       for line in b.get('lines',[]) for s in line['spans']]
                label=next(s for s in spans if s['text']=='VAT (20%):')
                amount=next(s for s in spans if s['text']=='€ 1,33')
                self.assertLess(abs(label['origin'][1]-amount['origin'][1]),0.2)
                self.assertIn(amount['font'], ('Helvetica', 'NimbusSans-Regular'))
                self.assertLess(label['bbox'][2], amount['bbox'][0])

    def test_fixed_vat_373_66(self):
        data=deepcopy(SAMPLE)
        data['items'][0].update({'unit_price':'10.99','quantity':34,'line_total':'373.66'})
        data['order_total']='373.66'
        n=mod.normalize(data)
        self.assertEqual(n['tax']['amount'],Decimal('62.28'))
        self.assertNotEqual(n['tax']['amount'],Decimal('74.73'))

    def test_invalid_vat_rejected(self):
        data=deepcopy(SAMPLE);data['tax']['amount']='1.60'
        with self.assertRaisesRegex(ValueError,'VAT-inclusive formula'):
            mod.normalize(data)

    def test_bad_math_rejected(self):
        data=deepcopy(SAMPLE);data['items'][0]['line_total']='9.99'
        with self.assertRaisesRegex(ValueError,'quantity × unit_price'):
            mod.normalize(data)

    def test_invalid_qty_rejected(self):
        data=deepcopy(SAMPLE);data['items'][0]['quantity']=0
        with self.assertRaises(ValueError):mod.normalize(data)

    def test_parse_amazon_text(self):
        txt='''| [403-1234567-7654321](https://example.test/order) | 买家姓名: | Entreprise Exemple | 配送渠道: 亚马逊 | 销售渠道: Amazon.fr | [Boa en Plumes Blanc 1,8 m](https://www.amazon.fr/gp/product/B000000000) | ASIN: B000000000 | SKU: DEMO-WHITE | 数量: 1 | 商品小计: €7.99 |\n**配送地址**\n| Camille EXEMPLE<br>10 Rue Exemple<br>batiment A<br>Lyon, 69000<br>法国 |'''
        d=mod.extract_order_text(txt)
        self.assertEqual(d['buyer']['name'],'Camille EXEMPLE')
        self.assertEqual(d['buyer']['postal_code'],'69000')
        self.assertEqual(d['buyer']['company'],'Entreprise Exemple')
        self.assertEqual(d['fulfillment'],'Amazon FBA')
        self.assertIn('Boa en Plumes',d['items'][0]['description'])

    def test_multisku_copy_rejected(self):
        with self.assertRaisesRegex(ValueError,'Multiple SKU'):
            mod.extract_order_text('403-1234567-7654321 SKU: A SKU: B')

    def test_long_fr_title_and_multiple_items(self):
        data=deepcopy(SAMPLE)
        data['items']=[dict(data['items'][0],sku=f'PRODUCT-{i}',quantity=1,unit_price='7.99',line_total='7.99',title='Boa en Plumes '+'Fête de Noël '*12) for i in range(5)]
        pdfs=self.render_text(data)
        self.assertEqual(len(pdfs),3)
        for pdf in pdfs:
            self.assertIn('Boa en Plumes',pdf)
        self.assertIn('39,95',pdfs[-1])
        self.assertEqual(''.join(pdfs).count('COMMERCIAL INVOICE'),3)

    def test_conflicting_seller_rejected(self):
        data=deepcopy(SAMPLE)
        data['seller']={'company':'Unrelated legal entity'}
        with self.assertRaisesRegex(ValueError,'Seller company differs'):
            self.render_text(data)

    def test_belgium_country_overwrites_old_france_text(self):
        data=deepcopy(SAMPLE)
        data['buyer']['country']='Belgium'
        data['buyer']['city']='Exempleville, Hainaut'
        data['buyer']['postal_code']='7560'
        text=self.render_text(data)[0]
        self.assertIn('Belgium',text)
        self.assertIn('Hainaut',text)
        self.assertIn('7560',text)
        self.assertNotIn('France',text)

    def test_shipping_discount_shows_net_and_reconciles_total(self):
        data=deepcopy(SAMPLE)
        data['shipping_fee']='0.75'
        data['shipping_discount']='0.75'
        data['order_total']='7.99'
        n=mod.normalize(data)
        self.assertEqual(n['shipping_net'],Decimal('0.00'))
        self.assertEqual(n['tax']['amount'],Decimal('1.33'))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'invoice.pdf'
            mod.invoice_pdf(n,path)
            with fitz.open(path) as doc:
                self.assertIn('0,00',doc[0].get_text())
                self.assertNotIn('·0,00',doc[0].get_text())

    def test_shipping_discount_requires_proper_amount(self):
        data=deepcopy(SAMPLE)
        data['shipping_fee']='0.75'
        data['shipping_discount']='0.99'
        with self.assertRaisesRegex(ValueError,'must not exceed'):
            mod.normalize(data)

    def test_bad_order_total_rejected_after_shipping_promotion(self):
        data=deepcopy(SAMPLE)
        data['shipping_fee']='0.75'
        data['shipping_discount']='0.50'
        data['order_total']='7.99'
        with self.assertRaisesRegex(ValueError,'does not match'):
            mod.normalize(data)

    def test_parse_belgium_order_with_shipping_promotion(self):
        txt='''| [402-1111111-2222222](https://example.test) | 买家姓名: | Morgan EXEMPLE | 销售渠道: Amazon.fr | [2 Planches de Strass](https://www.amazon.fr/gp/product/B000000000) |
**配送地址**
| Morgan EXEMPLE<br>Rue Fictive 4<br>Exempleville, Hainaut 7560<br>比利时 |
| [2 Planches de Strass Autocollants pour le Visage](https://www.amazon.fr/gp/product/B000000000) | 数量: 1 | 商品小计: €6.99 | 运费总额: €0.75 | 促销: -€0.75 | 商品总计: €6.99 |'''
        d=mod.extract_order_text(txt)
        self.assertEqual(d['buyer']['name'],'Morgan EXEMPLE')
        self.assertEqual(d['buyer']['country'],'Belgium')
        self.assertEqual(d['buyer']['postal_code'],'7560')
        self.assertIn('Hainaut',d['buyer']['city'])
        self.assertEqual(d['items'][0]['title'],'2 Planches de Strass Autocollants pour le Visage')
        self.assertEqual(d['shipping_fee'],'0.75')
        self.assertEqual(d['shipping_discount'],'0.75')
        self.assertEqual(d['order_total'],'6.99')

    def test_description_fallback_stays_nonempty(self):
        data=deepcopy(SAMPLE)
        data['items'][0]['description']=''
        text=self.render_text(data)[0]
        self.assertIn('Boa en Plumes Blanc',text)

    def test_non_euro_rejected_for_euro_template(self):
        data=deepcopy(SAMPLE)
        data['currency']='GBP'
        with self.assertRaisesRegex(ValueError,'fixed EUR'):
            mod.normalize(data)

    def test_seller_profile_address_mismatch_rejected(self):
        data=deepcopy(SAMPLE)
        data['seller']={'company':mod.SOURCE_SELLER_COMPANY,'address_lines':['Different seller address']}
        with self.assertRaisesRegex(ValueError,'seller.address_lines differs'):
            self.render_text(data)

    def test_no_real_buyer_in_sample(self):
        self.assertEqual(SAMPLE['buyer']['name'],'Camille EXEMPLE')
        self.assertEqual(SAMPLE['order_id'],'403-1234567-7654321')

    def test_renhaoyuan_template_selects_matching_legal_company(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='Renhaoyuan'
        data['buyer']['name']='Pickup EXEMPLE'
        data['buyer']['country']='Belgium'
        text=self.render_text(data)[0]
        self.assertIn('shenzhenshirenhaoyuanmaoyiyouxiangongsi',text)
        self.assertIn('Renhaoyuan',text)
        self.assertIn('+8613242020247',text)
        self.assertIn('renhaoyuanmaoyi@outlook.com',text)
        self.assertIn('longgangqu',text)
        self.assertIn('2B109',text)
        self.assertIn('Pickup EXEMPLE',text)
        self.assertIn('Belgium',text)
        for old in ['shenzhenshijiuyuekejiyouxiangongsi','+8617371452467','JiuYue_KeJi','Business registration','France']:
            self.assertNotIn(old,text)
        self.assertFalse(any('\u4e00' <= c <= '\u9fff' for c in text))

    def test_renhaoyuan_inferred_from_seller_identity(self):
        for identity in [
            {'company':'shenzhenshirenhaoyuanmaoyiyouxiangongsi'},
            {'store_name':'Renhaoyuan'},
            {'sales_name':'Renhaoyuan'},
        ]:
            with self.subTest(identity=identity):
                data=deepcopy(SAMPLE)
                data['seller']=identity
                normalized=mod.normalize(data)
                self.assertEqual(normalized['seller_template'],'renhaoyuan')
                self.assertIn('shenzhenshirenhaoyuanmaoyiyouxiangongsi',self.render_text(data)[0])

    def test_renhaoyuan_blank_country_can_fill_france(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='renhaoyuan'
        text=self.render_text(data)[0]
        self.assertEqual(text.count('France'),1)

    def test_cli_template_overrides_legacy_default(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)
            input_file=directory/'example.json'
            input_file.write_text(json.dumps(SAMPLE),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                mod.main(['--input',str(input_file),'--template','renhaoyuan','--output',str(directory)])
            with fitz.open(directory/f'{SAMPLE["order_id"]}.pdf') as doc:
                self.assertIn('shenzhenshirenhaoyuanmaoyiyouxiangongsi',doc[0].get_text())

    def test_conflicting_template_selectors_are_rejected(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='renhaoyuan'
        data['seller']={'company':mod.SOURCE_SELLER_COMPANY}
        with self.assertRaisesRegex(ValueError,'Conflicting seller template'):
            mod.normalize(data)
        data['seller']={}
        with self.assertRaisesRegex(ValueError,'Conflicting seller template'):
            mod.normalize(data,template='jiuyue')
        with self.assertRaisesRegex(ValueError,'Unknown seller template'):
            mod.normalize(data,template='../unapproved.pdf')

    def test_renhaoyuan_conflicting_contact_is_rejected(self):
        for field,value in [('tel','+0000000000'),('email','other@example.test'),('sales_name','Other seller')]:
            data=deepcopy(SAMPLE)
            data['seller_template']='renhaoyuan'
            data['seller']={field:value}
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,f'seller.{field} differs'):
                mod.normalize(data)

    def test_known_chinese_address_accepted_but_prints_pinyin(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='renhaoyuan'
        data['seller']={'address_lines':mod.SELLER_PROFILES['renhaoyuan']['source_address_lines']}
        text=self.render_text(data)[0]
        self.assertIn('huananguoji',text)
        self.assertFalse(any('\u4e00' <= c <= '\u9fff' for c in text))

    def test_renhaoyuan_blank_template_has_no_order_values(self):
        path=mod.TEMPLATE.parent/mod.SELLER_PROFILES['renhaoyuan']['template']
        with fitz.open(path) as doc:
            page=doc[0]
            text=page.get_text()
            self.assertNotIn('France',text)
            self.assertNotIn(SAMPLE['buyer']['name'],text)
            self.assertNotIn('Business registration',text)
            self.assertIsNone(re.search(r'\b\d{3}-\d{7}-\d{7}\b',text))
            self.assertIsNone(re.search(r'\b\d{2}/\d{2}/\d{4}\b',text))
            headings=[s for b in page.get_text('dict')['blocks'] for line in b.get('lines',[]) for s in line['spans']
                      if s['text']==mod.SELLER_PROFILES['renhaoyuan']['company']]
            self.assertEqual(len(headings),1)
            self.assertLess(headings[0]['bbox'][1],110)
            self.assertGreaterEqual(headings[0]['bbox'][0],10)
            self.assertLess(headings[0]['bbox'][2],page.rect.width-10)
            drawings=page.get_drawings()
            for x in mod.CELLS:
                self.assertTrue(any(abs(z['rect'].x0-x)<0.1 or abs(z['rect'].x1-x)<0.1 for z in drawings))

    def test_seller_profile_from_copied_text(self):
        raw='''403-1234567-7654321
| [Article Exemple](https://www.amazon.fr/gp/product/B000000000) | 数量: 1 | 商品小计: €7.99 |
购买日期: 2026年10月1日
销售渠道: Amazon.fr
配送地址
| Pickup EXEMPLE<br>Rue Exemple 10<br>Lyon, 69000<br>法国 |
Profil vendeur Amazon.fr : Renhaoyuan'''
        parsed=mod.extract_order_text(raw)
        self.assertEqual(mod.normalize(parsed)['seller_template'],'renhaoyuan')

    def test_renhaoyuan_multiple_items_keep_matching_seller(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='renhaoyuan'
        data['items']*=2
        texts=self.render_text(data)
        self.assertEqual(len(texts),1)
        for text in texts:
            self.assertIn('shenzhenshirenhaoyuanmaoyiyouxiangongsi',text)
            self.assertNotIn('shenzhenshijiuyuekejiyouxiangongsi',text)

    def test_missing_renhaoyuan_template_does_not_fall_back(self):
        data=deepcopy(SAMPLE)
        data['seller_template']='renhaoyuan'
        normalized=mod.normalize(data)
        original=mod.TEMPLATE
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            legacy=folder/'blank-reference-template.pdf'
            legacy.write_bytes(original.read_bytes())
            try:
                mod.TEMPLATE=legacy
                with self.assertRaisesRegex(FileNotFoundError,'blank-renhaoyuan-template.pdf'):
                    mod.invoice_pdf(normalized,folder/'invoice.pdf')
                self.assertFalse((folder/'invoice.pdf').exists())
            finally:
                mod.TEMPLATE=original

    def test_spanish_marketplace_portuguese_shipping_with_spanish_billing(self):
        data = deepcopy(SAMPLE)
        data['sales_channel'] = 'Amazon.es'
        data['buyer'].update(country='Portugal', postal_code='1000-001', city='Lisboa')
        data['billing_request'] = {'order_id': data['order_id'], 'buyer': {
            'name': 'BILLING EXAMPLE', 'country': 'Spain', 'postal_code': '28001',
            'city': 'Madrid', 'address_lines': ['Example street 1']}}
        data['items'][0].update(unit_price='10.99', line_total='10.99')
        data['order_total'] = '10.99'
        n = mod.normalize(data)
        self.assertEqual(n['tax']['rate'], '0.23')
        self.assertEqual(n['tax']['destination_country'], 'PT')
        self.assertEqual(n['tax']['destination_region'], 'mainland')
        self.assertEqual(n['tax']['rate_source'], 'shipping_destination')
        self.assertEqual(n['marketplace_code'], 'ES')
        self.assertEqual(n['buyer']['country'], 'Spain')
        self.assertEqual(n['net_amount'], Decimal('8.93'))
        self.assertEqual(n['tax']['amount'], Decimal('2.06'))
        text = self.render_text(data)[0]
        for value in ('Spain', 'VAT (23%):', 'Amount excl. VAT:', '€ 10,99', '€ 8,93', '€ 2,06'):
            self.assertIn(value, text)
        for old in ('VAT(20%*Price):', 'VAT (21%):'):
            self.assertNotIn(old, text)

    def test_portugal_regions_aliases_and_conflicting_evidence(self):
        for country in ('PT', 'Portugal', '葡萄牙'):
            for postal, region, rate in [('1000-001', 'mainland', '0.23'),
                                        ('9000-001', 'madeira', '0.22'),
                                        ('9400-001', 'madeira', '0.22'),
                                        ('9500-001', 'azores', '0.16')]:
                with self.subTest(country=country, postal=postal):
                    data = deepcopy(SAMPLE)
                    data['buyer'].update(country=country, postal_code=postal)
                    n = mod.normalize(data)
                    self.assertEqual(n['tax']['rate'], rate)
                    self.assertEqual(n['tax']['destination_region'], region)
                    self.assertEqual(n['net_amount'] + n['tax']['amount'], n['subtotal'])
        data['buyer'].update(postal_code='', tax_region='açores')
        self.assertEqual(mod.normalize(data)['tax']['rate'], '0.16')
        data['buyer']['postal_code'] = '1000-001'
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            mod.normalize(data)
        for changes in ({'postal_code': '', 'tax_region': ''}, {'tax_region': 'unknown'}):
            data['buyer'].update(changes)
            with self.assertRaises(ValueError):
                mod.normalize(data)

    def test_portugal_copied_order_preserves_shipping_postcode(self):
        raw = """403-1234567-7654321
销售渠道: Amazon.es
购买日期: 2026年10月1日
配送地址
| Example Buyer<br>Example Street 1<br>Lisboa, 1000-001<br>葡萄牙 |
| [Example Item](https://www.amazon.es/gp/product/B000000000) | 数量: 1 | 商品小计: €10.99 | 商品总计: €10.99 |"""
        data = mod.extract_order_text(raw)
        self.assertEqual(data['buyer']['country'], 'Portugal')
        self.assertEqual(data['buyer']['postal_code'], '1000-001')
        self.assertEqual(mod.normalize(data)['tax']['rate'], '0.23')

    def test_missing_shipping_country_never_uses_billing_country_or_site(self):
        for country in ('', 'Unknown'):
            data = self.pln_example()
            data['buyer']['country'] = country
            with self.subTest(country=country), self.assertRaisesRegex(ValueError, 'shipping destination'):
                mod.normalize(data)

    def test_net_vat_rounding_reconciles_and_footer_stays_inside_page(self):
        for currency in ('EUR', 'PLN'):
            for price in ('0.01', '0.03', '10.99', '9999.99'):
                with self.subTest(currency=currency, price=price), tempfile.TemporaryDirectory() as td:
                    data = deepcopy(SAMPLE)
                    data.update(currency=currency, sales_channel='Amazon.es', order_total=price)
                    data['buyer'].update(country='Portugal', tax_region='mainland', postal_code='1000-001')
                    data['items'][0].update(unit_price=price, line_total=price)
                    n = mod.normalize(data)
                    self.assertEqual(n['net_amount'] + n['tax']['amount'], Decimal(price))
                    path = Path(td) / 'invoice.pdf'
                    mod.invoice_pdf(n, path)
                    with fitz.open(path) as doc:
                        spans = [sp for b in doc[0].get_text('dict')['blocks'] for line in b.get('lines',[]) for sp in line['spans']]
                        for y in (639.29, 655.29, 671.29):
                            row = sorted([sp for sp in spans if abs(sp['origin'][1]-y)<0.2], key=lambda sp: sp['bbox'][0])
                            self.assertEqual(len(row), 2)
                            self.assertLess(row[0]['bbox'][2], row[1]['bbox'][0])
                            self.assertLessEqual(row[1]['bbox'][2], 550.2)
                            self.assertLess(row[1]['bbox'][3], 691)

if __name__=='__main__':
    unittest.main(verbosity=2)
