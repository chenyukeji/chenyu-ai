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
            self.assertEqual(mod.resolve_output_file(order_id, folder / 'invoice.pdf'), folder / f'{order_id}.pdf')
            self.assertEqual(mod.resolve_output_file(order_id, folder / 'Facture_sample.PDF'), folder / f'{order_id}.pdf')

    def test_cli_writes_invoice_named_with_order_number(self):
        order_id = SAMPLE['order_id']
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            input_file = folder / 'example.json'
            input_file.write_text(json.dumps(SAMPLE), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                mod.main(['--input', str(input_file), '--invoice-date', '2026-10-01',
                          '--output', str(folder / 'arbitrary-name.pdf')])
            files = list(folder.glob('*.pdf'))
            self.assertEqual([p.name for p in files], [f'{order_id}.pdf'])
            with fitz.open(files[0]) as pdf:
                self.assertIn('COMMERCIAL INVOICE', pdf[0].get_text())

    def test_date_comes_from_order_purchase_not_generation_date(self):
        data=deepcopy(SAMPLE)
        data['purchase_date']='2026-10-07'
        data['invoice_date']='2026-10-08'  # stale prior generated invoice date
        norm=mod.normalize(data)
        self.assertEqual(norm['invoice_date'],'2026-10-07')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'sample.pdf'
            mod.invoice_pdf(norm,path)
            with fitz.open(path) as doc:
                self.assertIn('07/10/2026',doc[0].get_text())
                self.assertNotIn('08/10/2026',doc[0].get_text())

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
        self.assertIn('VAT(20%*Price):',text)
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
                label=next(s for s in spans if s['text']=='VAT(20%*Price):')
                euro=next(s for s in spans if s['text'].strip()=='€' and 650 < s['origin'][1] < 675)
                amount=next(s for s in spans if s['text']=='1,33')
                self.assertLess(abs(label['origin'][1]-euro['origin'][1]),0.2)
                self.assertLess(abs(label['origin'][1]-amount['origin'][1]),0.2)
                self.assertEqual(amount['font'],'Helvetica')
                self.assertLess(abs(euro['bbox'][2]-amount['bbox'][0]),0.3)

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
        self.assertEqual(len(pdfs),5)
        for pdf in pdfs:
            self.assertIn('Boa en Plumes',pdf)
        self.assertIn('39,95',pdfs[-1])
        self.assertEqual(''.join(pdfs).count('COMMERCIAL INVOICE'),5)

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

if __name__=='__main__':
    unittest.main(verbosity=2)
