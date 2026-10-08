#!/usr/bin/env python3
"""Create a Chenyu-style Amazon commercial invoice from a verified JSON record or pasted order text.

Dependencies: pymupdf (pip install pymupdf). Uses the redacted original WPS invoice as a fixed-layout PDF template.
"""
from __future__ import annotations
import argparse
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import sys


CENT = Decimal('0.01')
VAT_RATE = Decimal('0.20')  # Fixed business template rule: VAT is included in Price
VAT_INCLUSIVE_DIVISOR = Decimal('1.20')
SHIPPING_WAY = 'Paypal package'  # Printed shipping method is fixed by the invoice template
CURRENCY = {'EUR': '€', 'GBP': '£', 'USD': '$'}


def money(v, field='amount'):
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        raise ValueError(f'{field}: invalid monetary value')
    try:
        d = Decimal(str(v).replace('€', '').replace('£', '').replace(' ', '').replace(',', '.'))
    except InvalidOperation as e:
        raise ValueError(f'{field}: not a decimal amount: {v}') from e
    if not d.is_finite() or d < 0 or d != d.quantize(CENT):
        raise ValueError(f'{field}: expected non-negative amount with at most two decimals')
    return d


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def inferred_description(title):
    """Only reuse factual words from the order title; never invent product details."""
    m=re.search(r'\bBoa en Plumes\s*\d+(?:[,.]\d+)?\s*m\b',title,re.I)
    if m:return m.group(0)
    # Generic fallback: beginning of the supplied product title before comma.
    s=clean(title).split(',')[0]
    return s if len(s)<=60 else ' '.join(s[:60].split()[:-1])

def extract_order_text(content):
    """Best-effort parser for a *single* Seller Central Chinese copied-order block.

    The assistant must confirm extraction before issuing a buyer-facing invoice.
    """
    s = content.replace('**', '')
    ids = re.findall(r'\b\d{3}-\d{7}-\d{7}\b', s)
    if not ids:
        raise ValueError('No Amazon order ID (123-1234567-1234567) found')
    if len(re.findall(r'\bSKU\s*:', s, flags=re.I)) > 1:
        raise ValueError('Multiple SKU sections found; provide structured JSON with items[]')
    out = {'order_id': ids[0], 'currency': 'EUR', 'items': [], 'buyer': {},
           'sales_channel': '', 'fulfillment': '', 'warnings': []}
    channel = re.search(r'销售渠道\s*:\s*\|?\s*(Amazon\.[a-z.]+)', s, re.I)
    if channel:
        out['sales_channel'] = channel.group(1)
    else:
        out['warnings'].append('Sales channel not detected')
    name = re.search(r'买家姓名\s*:\s*\|?\s*([^|\n]+)', s)
    if name:
        val = clean(name.group(1))
        if val and not val.startswith('---'):
            out['buyer']['company'] = val
    address = re.search(r'\*{0,2}配送地址\*{0,2}\s*\n+\s*\|\s*(.+?)\s*\|', s, re.S)
    if address:
        address_chunks = [clean(p) for p in re.split(r'<br\s*/?>', address.group(1), flags=re.I)]
        address_chunks = [v for v in address_chunks if v]
        if address_chunks:
            out['buyer']['name'] = address_chunks[0]
            if len(address_chunks) > 1:
                out['buyer']['country'] = {'法国':'France','比利时':'Belgium','德国':'Germany','意大利':'Italy','西班牙':'Spain'}.get(address_chunks[-1],address_chunks[-1])
                addr = address_chunks[1:-1]
                if addr:
                    last = re.match(r'^(.+?),?\s+(\d{4,6})$', addr[-1])
                    if last:
                        out['buyer']['city'] = clean(last.group(1).rstrip(','))
                        out['buyer']['postal_code'] = last.group(2)
                        addr.pop()
                    out['buyer']['address_lines'] = addr
    else:
        out['warnings'].append('Shipping address not detected')
    products = re.findall(r'\[([^\]]+)\]\(https?://www\.amazon\.[^)]+/gp/product/([A-Z0-9]{10})\)', s, re.I)
    product = max(products, key=lambda x: len(x[0])) if products else None
    sku = re.search(r'\bSKU\s*:\s*([^|\n]+)', s, re.I)
    asin = re.search(r'\bASIN\s*:\s*([A-Z0-9]{10})', s, re.I)
    qty = re.search(r'数量\s*:\s*\|?\s*(\d+)', s)
    subtotal = re.search(r'商品小计\s*:\s*\|?\s*[€£$]\s*([0-9.,]+)', s)
    if not product or not subtotal or not qty:
        raise ValueError('Product title, quantity or item subtotal missing; use structured JSON')
    quantity = int(qty.group(1))
    line_total = money(subtotal.group(1), '商品小计')
    if quantity <= 0:
        raise ValueError('Quantity must be positive')
    unit = (line_total / Decimal(quantity)).quantize(CENT, rounding=ROUND_HALF_UP)
    if unit * quantity != line_total:
        raise ValueError('Item subtotal cannot be divided evenly to a cent; confirm unit prices')
    out['items'] = [{'title': clean(product[0]),
                     'description': inferred_description(clean(product[0])), 'sku': clean(sku.group(1)) if sku else '',
                     'asin': (asin.group(1) if asin else product[1]),
                     'quantity': quantity, 'unit_price': str(unit),
                     'line_total': str(line_total)}]
    purchased = re.search(r'购买日期\s*:\s*\|?\s*(\d{4})年(\d{1,2})月(\d{1,2})日', s)
    if purchased:
        out['purchase_date'] = f'{int(purchased.group(1)):04d}-{int(purchased.group(2)):02d}-{int(purchased.group(3)):02d}'
    out['fulfillment'] = 'Amazon FBA' if re.search(r'(?:配送渠道|配送)\s*:\s*\|?\s*亚马逊', s) else ''
    fee = re.search(r'运费总额\s*:\s*\|?\s*€\s*([0-9.,]+)', s)
    promotion = re.search(r'促销\s*:\s*\|?\s*[-−]\s*€\s*([0-9.,]+)', s)
    grand = re.search(r'商品总计\s*:\s*\|?\s*€\s*([0-9.,]+)', s)
    if fee:
        out['shipping_fee'] = str(money(fee.group(1),'运费总额'))
    if promotion:
        out['shipping_discount'] = str(money(promotion.group(1),'促销'))
    if grand:
        out['order_total'] = str(money(grand.group(1),'商品总计'))
    if not fee:out['warnings'].append('Shipping fee unknown')
    if not grand:out['warnings'].append('Order grand total unknown')
    out['warnings'].extend(['VAT calculated using the template 20%-inclusive formula; confirm tax treatment',
                            'Country of manufacture unknown'])
    return out


def normalize(data, seller=None, invoice_date=None):
    if not isinstance(data, dict):
        raise ValueError('Input must be a JSON object')
    d = dict(data)
    if 'invoice_date' in d:
        raise ValueError('invoice_date is unsupported; use purchase_date')
    if not isinstance(d.get('buyer') or {}, dict) or not isinstance(d.get('seller') or {}, dict):
        raise ValueError('buyer and seller must be JSON objects')
    d['seller'] = dict(seller or {}) | dict(d.get('seller') or {})
    # The printed Date is ALWAYS the Amazon order purchase date, not the
    # PDF creation date or the Amazon dispatch/delivery deadline.
    purchase_date = clean(d.get('purchase_date'))
    if not purchase_date:
        raise ValueError('purchase_date is required: invoice Date must match the order purchase date')
    try:
        parsed_purchase = date.fromisoformat(purchase_date)
    except ValueError as e:
        raise ValueError('purchase_date must be YYYY-MM-DD') from e
    if invoice_date is not None and invoice_date != parsed_purchase.isoformat():
        raise ValueError('--invoice-date must match purchase_date; do not use generation date')
    d['purchase_date'] = parsed_purchase.isoformat()
    if not re.fullmatch(r'\d{3}-\d{7}-\d{7}', str(d.get('order_id', ''))):
        raise ValueError('Valid order_id is required')
    if d.get('currency', 'EUR') != 'EUR':
        raise ValueError('This exact source invoice has fixed EUR columns; use EUR only')
    d.setdefault('currency', 'EUR')
    if not isinstance(d.get('items'), list) or not d['items']:
        raise ValueError('At least one item is required')
    checked = []
    for i, item in enumerate(d['items'], 1):
        if not clean(item.get('title')):
            raise ValueError(f'items[{i}].title is required')
        try:
            qty = int(item['quantity'])
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError(f'items[{i}].quantity is invalid') from e
        if qty < 1 or str(item['quantity']) != str(qty):
            raise ValueError(f'items[{i}].quantity must be a positive integer')
        unit = money(item.get('unit_price'), f'items[{i}].unit_price')
        line = money(item.get('line_total'), f'items[{i}].line_total')
        if unit is None or line is None:
            raise ValueError(f'items[{i}]: unit_price and line_total required')
        if unit * qty != line:
            raise ValueError(f'items[{i}]: quantity × unit_price != line_total')
        checked.append({**item, 'quantity': qty, 'unit_price': unit, 'line_total': line})
    d['items'] = checked
    # Keep fulfillment as source metadata, but always print the template's fixed shipping method.
    d['shipping_way'] = SHIPPING_WAY
    subtotal = sum((i['line_total'] for i in checked), Decimal('0'))
    shipping = money(d.get('shipping_fee'), 'shipping_fee')
    order_total = money(d.get('order_total'), 'order_total')
    tax = d.get('tax') or {}
    if not isinstance(tax, dict):
        raise ValueError('tax must be an object')
    supplied_tax = money(tax.get('amount'), 'tax.amount')
    shipping_discount = money(d.get('shipping_discount'), 'shipping_discount') or Decimal('0.00')
    if shipping is None and shipping_discount:
        raise ValueError('shipping_discount requires a known shipping_fee')
    if shipping is not None and shipping_discount > shipping:
        raise ValueError('shipping_discount must not exceed shipping_fee')
    shipping_net = (shipping - shipping_discount) if shipping is not None else None
    if order_total is not None and shipping_net is not None:
        expected_total = subtotal + shipping_net
        if order_total != expected_total:
            raise ValueError(f'Order total {order_total:.2f} does not match goods plus '
                             f'net shipping {expected_total:.2f}; check promotional discounts')
    # Price is VAT-inclusive. Always use Price / 1.2 * 0.2, never Price * 0.2.
    # Prefer a confirmed order total; otherwise calculate on the confirmed goods subtotal.
    vat_basis = 'order_total' if order_total is not None else 'items_subtotal'
    price = order_total if order_total is not None else subtotal
    tax_amount = (price / VAT_INCLUSIVE_DIVISOR * VAT_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
    if supplied_tax is not None and supplied_tax != tax_amount:
        raise ValueError(f'tax.amount {supplied_tax:.2f} disagrees with the fixed '
                         f'VAT-inclusive formula ({tax_amount:.2f} on {vat_basis})')
    d['subtotal'] = subtotal
    d['shipping_fee'] = shipping
    d['shipping_discount'] = shipping_discount
    d['shipping_net'] = shipping_net
    d['order_total'] = order_total
    d['tax'] = {**tax, 'amount': tax_amount, 'rate': '0.20',
                'calculation': 'Price / 1.2 * 0.2', 'basis': vat_basis}
    warnings = [w for w in d.get('warnings', []) if isinstance(w, str)]
    for key, message in [('buyer','Buyer details missing'), ('seller','Seller details missing')]:
        if not isinstance(d.get(key), dict) or not d[key]:
            warnings.append(message)
    if not d['seller'].get('company'):
        warnings.append('Seller legal name missing')
    if not d.get('buyer', {}).get('address_lines'):
        warnings.append('Buyer street address missing')
    if order_total is None:
        warnings.append('Order grand total not provided; only items subtotal known')
    if shipping is None:
        warnings.append('Shipping fee not provided')
    if vat_basis == 'items_subtotal':
        warnings.append('VAT is calculated on goods subtotal only; order total/shipping may be incomplete')
        warnings.append('Reference template Total Amount displays known goods subtotal; payment grand total not verified')
    warnings.append('20% VAT-inclusive calculation is the supplied business template rule, not tax status verification')
    if not d.get('origin'):
        warnings.append('Country of manufacture not confirmed')
    d['warnings'] = list(dict.fromkeys(warnings))
    return d


# This renderer fills a buyer-free copy of the ACTUAL WPS source PDF. It never
# redraws the header or table: the original geometry, type, line strokes, grey
# cells, and footer stay identical to the user's reference document.
import pymupdf as fitz

TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'blank-reference-template.pdf'
SOURCE_SELLER_COMPANY = 'shenzhenshijiuyuekejiyouxiangongsi'
FONT_SERIF = 'tiro'   # PDF built-in Times-Roman, closest to source TimesNewRoman
FONT_BOLD = 'tibo'    # PDF built-in Times-Bold
FONT_SANS = 'helv'    # PDF built-in Helvetica, close to source Arial
FONT_SANS_BOLD = 'hebo'
FONT_MONO = 'cour'
CELLS = [9.9,65.3,122.3,288.8,381.9,460.55,507.05,558.9]
ROW_TOP, ROW_BOTTOM = 500.8, 610.49


def number_fmt(value):
    return f'{value:.2f}'.replace('.', ',')


def wrap_to_width(text, font, size, max_width):
    font_obj=fitz.Font(fontname=font)
    result=[]
    for para in str(text or '').replace('\r','').split('\n'):
        if not para.strip():
            continue
        line=''
        for word in para.split():
            candidate=(line+' '+word).strip()
            if font_obj.text_length(candidate,fontsize=size) <= max_width:
                line=candidate
                continue
            if line:result.append(line)
            line=''
            for letter in word:
                if font_obj.text_length(line+letter,fontsize=size) <= max_width:
                    line += letter
                else:
                    if line: result.append(line)
                    line=letter
        if line:result.append(line)
    return result


def fit_lines(text, font, max_width, max_height, *, ideal=12, minimum=8.5, lead=1.3):
    size=ideal
    while size>=minimum-0.001:
        lines=wrap_to_width(text,font,size,max_width)
        height=size + max(0,len(lines)-1)*size*lead
        if height <= max_height:
            return lines,round(size,2),size*lead
        size-=0.25
    raise ValueError('Invoice field does not fit reference layout; shorten product description or address')


def draw_centered_lines(page,text, x1, x2, y1, y2, *, font=FONT_BOLD, ideal=12, minimum=9):
    if not clean(text):return
    lines,size,leading=fit_lines(text,font,(x2-x1)-6,y2-y1-6,ideal=ideal,minimum=minimum)
    # Baseline centre matches Times New Roman original product-cell geometry.
    y0=(y1+y2)/2 + size*0.32 - (len(lines)-1)*leading/2
    for n,line in enumerate(lines):
        width=fitz.get_text_length(line,fontname=font,fontsize=size)
        page.insert_text(((x1+x2-width)/2,y0+n*leading),line,fontname=font,fontsize=size,overlay=True)


def draw_left(page,text,x,y,*,font=FONT_BOLD,size=12, max_width=None, minsize=8):
    if not clean(text):return
    s=clean(text)
    if max_width is not None:
        while size>minsize and fitz.get_text_length(s,fontname=font,fontsize=size)>max_width:
            size-=0.25
        if fitz.get_text_length(s,fontname=font,fontsize=size)>max_width:
            raise ValueError('Field is too long for the exact invoice template: '+s[:60])
    page.insert_text((x,y),s,fontname=font,fontsize=size,overlay=True)


def draw_address(page, buyer):
    """Address lists street/building ONLY; recipient prints on buyer heading.

    Retain the original blank Contact and Company Name rows. Accept a
    duplicated recipient at the beginning of address_lines and omit it.
    """
    name = clean(buyer.get('name', ''))
    streets = [clean(x) for x in buyer.get('address_lines', []) if clean(x)]
    if name and streets and streets[0].casefold() == name.casefold():
        streets.pop(0)
    if not streets:
        return
    if len(streets) > 3:
        raise ValueError('Street address exceeds 3 printed lines in exact template')
    font = FONT_BOLD
    size = 11.0 if len(streets) <= 2 else 9.55
    max_width = 267
    for line in streets:
        if fitz.get_text_length(line, fontname=font, fontsize=size) > max_width:
            raise ValueError('Street line too long for original template: ' + line)
    if len(streets) == 3:
        baselines = [308.4, 319.3, 330.2]
    elif len(streets) == 2:
        baselines = [314.0, 329.5]
    else:
        baselines = [318.8]
    for line, y in zip(streets, baselines):
        draw_left(page, line, 106.92, y, font=font, size=size)


def validate_seller_against_template(seller):
    company=clean(seller.get('company',''))
    if company and company.casefold()!=SOURCE_SELLER_COMPANY.casefold():
        raise ValueError('Seller company differs from exact reference template; use another approved seller template')
    # Source PDF carries verified static phone and sales name. Reject conflicting overrides.
    if seller.get('address_lines'):
        expected=['ADD: pinghujiedaoshangmugucun116hao305',
                  'shenzhenshi, longgangqu, Guangdong 518111','CN']
        supplied=[clean(x) for x in seller['address_lines']]
        if supplied != expected:
            raise ValueError('seller.address_lines differs from the original seller letterhead')
    for k,reference in [('tel','+8617371452467'),('sales_name','JiuYue_KeJi')]:
        value=clean(seller.get(k,''))
        if value and value!=reference:
            raise ValueError(f'seller.{k} differs from the source template, which has fixed business letterhead')


def invoice_pdf(d,output):
    template=Path(TEMPLATE)
    if not template.is_file():
        raise FileNotFoundError(f'Missing bundled original-layout template: {template}')
    if d['currency']!='EUR':
        raise ValueError('This exact-match template has printed € headings; only EUR orders may use it')
    seller=d.get('seller') or {}
    validate_seller_against_template(seller)
    buyer=d.get('buyer') or {}
    doc=fitz.open(template)
    # One item per copy of the original PDF page retains the exact fixed row size.
    # Multiple items do not shrink the table to illegible proportions.
    for n,item in enumerate(d['items']):
        if n:
            doc.insert_pdf(fitz.open(template))
        page=doc[n]
        # Recipient name is the only value printed after Importer/Buyer/Receiver.
        # Order buyer's "Entreprise Exemple" is NOT a name and is not printed here.
        # Keep both original labels Contact: and Company Name: with blank values.
        name=clean(buyer.get('name',''))
        if not name:
            raise ValueError('buyer.name required for Importer/Buyer/Receiver heading')
        draw_left(page,name,157.0,256.2,font=FONT_BOLD,size=12,max_width=224)
        draw_address(page,buyer)
        draw_left(page,buyer.get('city',''),106.9,347.2,font=FONT_BOLD,size=12,max_width=265)
        # The approved blank mother PDF visibly includes the source sample's France.
        # Keep that lettering completely unmodified for French orders; for Belgian
        # (and other) addresses replace only that word, not the column geometry.
        country=clean(buyer.get('country',''))
        country_labels={'法国':'France','比利时':'Belgium','德国':'Germany',
                        '意大利':'Italy','西班牙':'Spain','英国':'United Kingdom'}
        country=country_labels.get(country,country)
        if not country:
            raise ValueError('buyer.country is required; cannot assume France')
        if country.casefold() != 'france':
            page.add_redact_annot(fitz.Rect(106.4,359.0,178.0,377.0),fill=(1,1,1))
            page.apply_redactions(images=0,graphics=0,text=0)
            draw_left(page,country,106.92,372.65,font=FONT_BOLD,size=12,max_width=210)
        draw_left(page,buyer.get('postal_code',''),106.92,391.6,font=FONT_BOLD,size=12,max_width=120)
        draw_left(page,buyer.get('tel',''),39.3,406.8,font=FONT_BOLD,size=11,max_width=260)
        remote=buyer.get('remote_area')
        if remote is not None:
            draw_left(page,'Yes' if remote else 'No',83.9,422.8,font=FONT_SANS_BOLD,size=10.4)
        draw_left(page,d.get('tracking_number',''),100,454.4,font=FONT_SANS,size=9,max_width=252)
        vatnum=clean(seller.get('vat_number',''))
        if vatnum:draw_left(page,vatnum,450.0,406.6,font=FONT_SANS,size=9,max_width=100)
        issue=date.fromisoformat(d['purchase_date']).strftime('%d/%m/%Y')
        draw_left(page,issue,411.4,422.8,font=FONT_SANS_BOLD,size=9.9,max_width=85)
        # Seven column borders, grey header and 110-pt table row remain unchanged.
        draw_centered_lines(page,str(n+1),CELLS[0],CELLS[1],ROW_TOP,ROW_BOTTOM,font=FONT_SERIF,ideal=12)
        # The reference Item No. is the Amazon ORDER number (not SKU): 3 centred lines.
        order_id=d['order_id']
        order_text=order_id[:8]+'\n'+order_id[8:16]+'\n'+order_id[16:]
        draw_centered_lines(page,order_text,CELLS[1],CELLS[2],ROW_TOP,ROW_BOTTOM,font=FONT_SERIF,ideal=12)
        draw_centered_lines(page,item['title'],CELLS[2],CELLS[3],ROW_TOP,ROW_BOTTOM,font=FONT_BOLD,ideal=12,minimum=9)
        description=clean(item.get('description')) or inferred_description(item['title'])
        draw_centered_lines(page,description,CELLS[3],CELLS[4],ROW_TOP,ROW_BOTTOM,font=FONT_BOLD,ideal=12,minimum=8)
        draw_centered_lines(page,number_fmt(item['unit_price']),CELLS[4],CELLS[5],ROW_TOP,ROW_BOTTOM,font=FONT_SERIF,ideal=12)
        draw_centered_lines(page,str(item['quantity']),CELLS[5],CELLS[6],ROW_TOP,ROW_BOTTOM,font=FONT_SERIF,ideal=12)
        draw_centered_lines(page,number_fmt(item['line_total']),CELLS[6],CELLS[7],ROW_TOP,ROW_BOTTOM,font=FONT_SERIF,ideal=12)
        if n==len(d['items'])-1:
            # Exact source label 'Total Amount: €' is preserved, goods subtotal
            # shown when the actual final payment amount was not provided.
            price=d['order_total'] if d['order_total'] is not None else d['subtotal']
            draw_left(page,number_fmt(price),469.0,639.0,font=FONT_SANS,size=9.9,max_width=76)
            # The template's VAT label and euro sign share the SAME text baseline:
            # 664.13 pt.  Keep the amount on that baseline as well.  Use a
            # proportionally spaced sans-serif face matching the Arial label,
            # rather than Courier's wider glyph spacing and lower baseline.
            draw_left(page,number_fmt(d['tax']['amount']),506.4,664.13,
                      font=FONT_SANS,size=9.95,max_width=38)
            if clean(d.get('origin')):
                draw_left(page,d['origin'],54.2,688.4,font=FONT_SANS_BOLD,size=9.9,max_width=175)
            # The single 'Shipping fee' field shows NET shipping after a
            # documented shipping promotion, so it reconciles with Total Amount.
            shipping=d.get('shipping_net')
            if shipping is not None:
                draw_left(page,number_fmt(shipping),445.0,622.0,font=FONT_SANS,size=9.9,max_width=70)
        else:
            draw_left(page,f'Page {n+1}/{len(d["items"])}',496.0,716.0,font=FONT_SANS,size=8.5)
    doc.set_metadata({'title':f'COMMERCIAL INVOICE {d["order_id"]}', 'author':'Chenyu Commercial Invoice'})
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    doc.save(str(output),garbage=4,deflate=True)
    doc.close()


def resolve_output_file(order_id, requested=None):
    """Save the invoice under its Amazon order ID in the requested directory."""
    directory = Path(requested) if requested is not None else Path.cwd()
    if directory.suffix.lower() == '.pdf':
        raise ValueError('--output must be a directory')
    return directory / f'{order_id}.pdf'


def main(argv=None):
    p=argparse.ArgumentParser(description='Amazon order to template-style commercial invoice PDF')
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--input',type=Path,help='Order JSON file')
    g.add_argument('--text',type=Path,help='Copied order text/Markdown (single item)')
    p.add_argument('--seller',type=Path,help='Private seller profile JSON (not checked into Git)')
    p.add_argument('--invoice-date',help='Optional confirmation of purchase date YYYY-MM-DD; must match purchase_date')
    p.add_argument('--output',type=Path,help='Output directory; filename is always <order_id>.pdf')
    args=p.parse_args(argv)
    try:
        payload=(json.loads(args.input.read_text(encoding='utf-8')) if args.input else
                 extract_order_text(args.text.read_text(encoding='utf-8')))
        seller=json.loads(args.seller.read_text(encoding='utf-8')) if args.seller else None
        d=normalize(payload,seller=seller,invoice_date=args.invoice_date)
        output_path = resolve_output_file(d['order_id'], args.output)
        output_path.parent.mkdir(parents=True,exist_ok=True)
        invoice_pdf(d,output_path)
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as e:
        p.exit(2,f'ERROR: {e}\n')
    print(f'Invoice PDF: {output_path}')
    for w in d['warnings']:
        print('REVIEW: '+w,file=sys.stderr)

if __name__ == '__main__':
    main()
