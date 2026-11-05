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
from urllib.parse import urlsplit


CENT = Decimal('0.01')
# User-supplied business rates, not an automatic determination of tax treatment.
DESTINATION_VAT_RATES = {code: Decimal(rate) for code, rate in {
    'UK': '0.20', 'DE': '0.19', 'FR': '0.20', 'IT': '0.22', 'ES': '0.21',
    'NL': '0.21', 'PL': '0.23', 'CZ': '0.21', 'AT': '0.20', 'BE': '0.21', 'PT': '0.23',
}.items()}
SALES_CHANNEL_SITES = {
    'amazon.co.uk': 'UK', 'amazon.de': 'DE', 'amazon.fr': 'FR',
    'amazon.it': 'IT', 'amazon.es': 'ES', 'amazon.nl': 'NL',
    'amazon.pl': 'PL', 'amazon.com.be': 'BE',
}
MARKETPLACE_CODES = {'UK', 'DE', 'FR', 'IT', 'ES', 'NL', 'PL', 'CZ', 'AT', 'BE'}
COUNTRY_NAMES = {
    'UK': ('United Kingdom', 'GB', '英国'), 'DE': ('Germany', 'Deutschland', '德国'),
    'FR': ('France', '法国'), 'IT': ('Italy', 'Italia', '意大利'),
    'ES': ('Spain', 'España', '西班牙'), 'NL': ('Netherlands', 'Nederland', '荷兰'),
    'PL': ('Poland', 'Polska', '波兰'), 'CZ': ('Czechia', 'Czech Republic', '捷克'),
    'AT': ('Austria', 'Österreich', '奥地利'), 'BE': ('Belgium', 'Belgique', 'België', '比利时'),
    'PT': ('Portugal', '葡萄牙'),
}
COUNTRY_CODES = {alias.casefold(): code for code, names in COUNTRY_NAMES.items() for alias in (code, *names)}
PT_REGIONS = {
    'mainland': ('mainland', 'continental', 'continente', 'portugal continental', '葡萄牙大陆'),
    'madeira': ('madeira', 'pt-30', '马德拉'),
    'azores': ('azores', 'açores', 'acores', 'pt-20', '亚速尔'),
}
PT_RATES = {'mainland': Decimal('0.23'), 'madeira': Decimal('0.22'), 'azores': Decimal('0.16')}


SHIPPING_WAY = 'Paypal package'  # Printed shipping method is fixed by the invoice template
CURRENCY = {'EUR': '€', 'PLN': 'PLN'}


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


def resolve_marketplace(data):
    """Validate sales-channel metadata independently of destination VAT."""
    channel = clean(data.get('sales_channel'))
    explicit = clean(data.get('marketplace_code')).upper()
    if explicit and explicit not in MARKETPLACE_CODES:
        raise ValueError(f'Unknown marketplace_code: {explicit}')
    site = None
    if channel:
        host = urlsplit(channel if '://' in channel else '//' + channel).hostname or ''
        host = host.lower().removeprefix('www.')
        site = SALES_CHANNEL_SITES.get(host)
        if site is None:
            raise ValueError(f'Unknown sales_channel: {channel}; confirm the order marketplace')
        if explicit and explicit != site:
            raise ValueError('sales_channel conflicts with marketplace_code')
    site = site or explicit
    if not site:
        raise ValueError('sales_channel or confirmed marketplace_code is required; do not infer the marketplace')
    return site


def resolve_destination_vat(buyer):
    """Use original shipping evidence, never invoice-address or marketplace country."""
    country = COUNTRY_CODES.get(clean(buyer.get('country')).casefold())
    if country is None:
        raise ValueError('buyer.country must identify a supported shipping destination; cannot fall back to marketplace')
    region = ''
    rate = DESTINATION_VAT_RATES[country]
    if country == 'PT':
        supplied = clean(buyer.get('tax_region')).casefold()
        if supplied:
            region = next((key for key, aliases in PT_REGIONS.items() if supplied in aliases), '')
            if not region:
                raise ValueError('buyer.tax_region for Portugal must be mainland, madeira or azores')
        postal = clean(buyer.get('postal_code'))
        inferred = ''
        if re.fullmatch(r'[1-9]\d{3}-?\d{3}', postal):
            prefix = int(postal[:2])
            inferred = 'azores' if prefix >= 95 else 'madeira' if prefix >= 90 else 'mainland'
        if inferred and region and inferred != region:
            raise ValueError('Portuguese shipping postal_code conflicts with tax_region')
        region = region or inferred
        if not region:
            raise ValueError('Portugal requires a verified shipping postal_code or buyer.tax_region')
        rate = PT_RATES[region]
    return country, region, rate


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
    if len(set(ids)) != 1:
        raise ValueError('Conflicting order IDs; provide one verified order')
    if re.search(r'Dane do faktury|开票资料|开票信息|账单地址|billing address', s, re.I):
        raise ValueError('Buyer invoice message detected; verify it into structured JSON billing_request')
    out = {'order_id': ids[0], 'currency': '', 'items': [], 'buyer': {},
           'sales_channel': '', 'fulfillment': '', 'warnings': []}
    channels = set(re.findall(r'销售渠道\s*[:：]\s*\|?\s*(Amazon\.[a-z.]+)', s, re.I))
    channels = {value.lower() for value in channels}
    if len(channels) > 1:
        raise ValueError('Conflicting sales channels; provide one verified order')
    if channels:
        out['sales_channel'] = channels.pop()
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
                out['buyer']['country'] = {'法国':'France','比利时':'Belgium','德国':'Germany','意大利':'Italy','西班牙':'Spain','葡萄牙':'Portugal'}.get(address_chunks[-1],address_chunks[-1])
                addr = address_chunks[1:-1]
                if addr:
                    last = re.match(r'^(.+?),?\s+(\d{4}-\d{3}|\d{2}-\d{3}|\d{7}|\d{4,6})$', addr[-1])
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
    amount_pattern = r'(?:(€|£|\$|PLN|zł)\s*([0-9.,]+)|([0-9.,]+)\s*(€|£|\$|PLN|zł))'
    subtotal = re.search(r'(?:商品小计|Item subtotal)\s*[:：]\s*\|?\s*' + amount_pattern, s, re.I)
    if not product or not subtotal or not qty:
        raise ValueError('Product title, quantity or item subtotal missing; use structured JSON')
    quantity = int(qty.group(1))
    symbols = {'€': 'EUR', '£': 'GBP', '$': 'USD', 'PLN': 'PLN', 'zł': 'PLN'}
    out['currency'] = symbols[subtotal.group(1) or subtotal.group(4)]
    line_total = money(subtotal.group(2) or subtotal.group(3), '商品小计')
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
    for label, field in [('运费总额', 'shipping_fee'), ('促销', 'shipping_discount'), ('(?:商品总计|Item total)', 'order_total')]:
        sign = r'[-−]\s*' if field == 'shipping_discount' else ''
        matched = re.search(label + r'\s*[:：]\s*\|?\s*' + sign + amount_pattern, s, re.I)
        if matched:
            if symbols[matched.group(1) or matched.group(4)] != out['currency']:
                raise ValueError('Conflicting currencies in order amounts')
            out[field] = str(money(matched.group(2) or matched.group(3), label))
            if field == 'order_total':
                out['amount_source'] = 'displayed_item_total'
    seller_profile = re.search(r'Profil vendeur Amazon\.fr\s*[:：]\s*([^\r\n|]+)', s, re.I)
    if seller_profile:
        out['seller_template'] = clean(seller_profile.group(1))
    if 'shipping_fee' not in out:out['warnings'].append('Shipping fee unknown')
    if 'order_total' not in out:out['warnings'].append('Order grand total unknown')
    out['warnings'].append('Country of manufacture unknown')
    return out


def normalize(data, seller=None, invoice_date=None, template=None):
    if not isinstance(data, dict):
        raise ValueError('Input must be a JSON object')
    d = dict(data)
    if 'invoice_date' in d:
        raise ValueError('invoice_date is unsupported; use purchase_date')
    if not isinstance(d.get('buyer') or {}, dict) or not isinstance(d.get('seller') or {}, dict):
        raise ValueError('buyer and seller must be JSON objects')
    d['seller'] = dict(seller or {}) | dict(d.get('seller') or {})
    d['seller_template'] = resolve_seller_template(d, template)
    validate_seller_against_template(d['seller'], d['seller_template'])
    if d['seller_template'] == 'imported' and d.get('seller_confirmed') is not True:
        raise ValueError('Imported seller requires seller_confirmed from a verified saved profile or explicit confirmation')
    profile = SELLER_PROFILES.get(d['seller_template'], {})
    d['seller'] = {key: profile[key] for key in ['company', 'tel', 'sales_name', 'email', 'store_name']
                   if key in profile} | d['seller']
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
    validate_currency(d)
    shipping_destination = dict(d.get('buyer') or {})
    if 'billing_request' in d:
        request = d['billing_request']
        if not isinstance(request, dict) or request.get('order_id') != d['order_id']:
            raise ValueError('billing_request must refer to the same order_id')
        billing = request.get('buyer')
        if not isinstance(billing, dict):
            raise ValueError('billing_request.buyer must contain verified invoice details')
        for field in ('name', 'city', 'postal_code', 'country'):
            if not isinstance(billing.get(field), str) or not billing[field].strip():
                raise ValueError(f'billing_request.buyer.{field} is required; do not substitute shipping details')
        streets = billing.get('address_lines')
        if not isinstance(streets, list) or not streets or any(not isinstance(line, str) or not line.strip() for line in streets):
            raise ValueError('billing_request.buyer.address_lines is required')
        d['shipping_buyer'] = dict(d.get('buyer') or {})
        d['buyer'] = dict(billing)
        d['buyer_source'] = 'buyer_invoice_message'
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
    # Price is VAT-inclusive; use the original delivery destination, before billing overrides.
    # Prefer a confirmed order total; otherwise calculate on the confirmed goods subtotal.
    site = resolve_marketplace(d)
    destination, region, rate = resolve_destination_vat(shipping_destination)
    if tax.get('rate') not in (None, ''):
        try:
            supplied_rate = Decimal(str(tax['rate']))
        except InvalidOperation as e:
            raise ValueError('tax.rate must be a decimal fraction, e.g. 0.19') from e
        if not supplied_rate.is_finite() or supplied_rate != rate:
            raise ValueError(f'tax.rate conflicts with {destination} destination rate {rate}')
    divisor = Decimal('1') + rate
    vat_basis = 'order_total' if order_total is not None else 'items_subtotal'
    price = order_total if order_total is not None else subtotal
    tax_amount = (price / divisor * rate).quantize(CENT, rounding=ROUND_HALF_UP)
    if supplied_tax is not None and supplied_tax != tax_amount:
        raise ValueError(f'tax.amount {supplied_tax:.2f} disagrees with the {destination} '
                         f'VAT-inclusive formula ({tax_amount:.2f} on {vat_basis})')
    d['subtotal'] = subtotal
    d['shipping_fee'] = shipping
    d['shipping_discount'] = shipping_discount
    d['shipping_net'] = shipping_net
    d['order_total'] = order_total
    d['marketplace_code'] = site
    d['net_amount'] = price - tax_amount
    d['tax'] = {**tax, 'amount': tax_amount, 'rate': str(rate),
                'calculation': f'Price / {divisor.normalize()} * {rate.normalize()}', 'basis': vat_basis,
                'destination_country': destination, 'destination_region': region,
                'rate_source': 'shipping_destination'}
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
    warnings.append(f'{destination} {region} {rate:.0%} VAT-inclusive calculation uses the supplied destination rate table, not tax status verification')
    if not d.get('origin'):
        warnings.append('Country of manufacture not confirmed')
    d['warnings'] = list(dict.fromkeys(warnings))
    return d


# This renderer fills a buyer-free copy of the ACTUAL WPS source PDF. It never
# redraws the header or table: the original geometry, type, line strokes, grey
# cells stay identical; the footer adds the approved net-amount line.
import pymupdf as fitz

TEMPLATE = Path(__file__).resolve().parent.parent / 'assets' / 'blank-reference-template.pdf'
SOURCE_SELLER_COMPANY = 'shenzhenshijiuyuekejiyouxiangongsi'
SELLER_PROFILES = json.loads((TEMPLATE.parent / 'seller-templates.json').read_text(encoding='utf-8'))
FONT_SERIF = 'tiro'   # PDF built-in Times-Roman, closest to source TimesNewRoman
FONT_BOLD = 'tibo'    # PDF built-in Times-Bold
FONT_SANS = 'helv'    # PDF built-in Helvetica, close to source Arial
FONT_SANS_BOLD = 'hebo'
FONT_MONO = 'cour'
CELLS = [9.9,65.3,122.3,288.8,381.9,460.55,507.05,558.9]
ROW_TOP, ROW_BOTTOM = 500.8, 610.49


def number_fmt(value):
    return f'{value:.2f}'.replace('.', ',')


def validate_currency(data):
    currency = data.get('currency')
    if currency not in CURRENCY:
        raise ValueError('Explicit supported currency required: EUR or PLN; fixed EUR must not relabel other currencies')
    template_currency = data.get('template_currency')
    if template_currency is not None and template_currency != currency:
        raise ValueError('template_currency conflicts with original order currency; do not convert or relabel amounts')


def insert_text(page, point, value, font, size):
    face = fitz.Font(fontname=font)
    if any(not face.has_glyph(ord(char)) for char in value if not char.isspace()):
        raise ValueError('Unsupported glyph in invoice field; use a verified compatible font')
    if any(ord(char) > 255 for char in value):
        resource = 'Invoice' + font
        page.insert_font(fontname=resource, fontbuffer=face.buffer)
        font = resource
    page.insert_text(point, value, fontname=font, fontsize=size, overlay=True)


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
        insert_text(page, ((x1+x2-width)/2,y0+n*leading), line, font, size)


def draw_left(page,text,x,y,*,font=FONT_BOLD,size=12, max_width=None, minsize=8):
    if not clean(text):return
    s=clean(text)
    if max_width is not None:
        while size>minsize and fitz.get_text_length(s,fontname=font,fontsize=size)>max_width:
            size-=0.25
        if fitz.get_text_length(s,fontname=font,fontsize=size)>max_width:
            raise ValueError('Field is too long for the exact invoice template: '+s[:60])
    insert_text(page, (x,y), s, font, size)


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


def resolve_seller_template(data, requested=None):
    """Select only approved profiles; conflicting selectors never cross seller identities."""
    def find(value):
        if clean(value).casefold() == 'imported':
            return 'imported'
        for key, profile in SELLER_PROFILES.items():
            aliases = [key, profile['company'], *profile.get('aliases', [])]
            if clean(value).casefold() in [clean(alias).casefold() for alias in aliases]:
                return key
        return None

    choices = []
    for value in [requested, data.get('seller_template')]:
        if clean(value):
            key = find(value)
            if key is None:
                raise ValueError(f'Unknown seller template: {value}; use an approved seller template')
            choices.append(key)
    seller = data.get('seller') or {}
    for field in ['company', 'store_name', 'sales_name']:
        value = clean(seller.get(field))
        if value:
            key = find(value)
            if key is not None:
                choices.append(key)
            elif field == 'store_name' and 'imported' not in choices:
                raise ValueError(f'Unknown seller store: {value}; use an approved seller template')
    if len(set(choices)) > 1:
        raise ValueError('Conflicting seller template selections; confirm the order seller')
    return choices[0] if choices else 'jiuyue'


def validate_seller_against_template(seller, template_id='jiuyue'):
    if template_id == 'imported':
        if not isinstance(seller.get('company'), str) or not seller['company'].strip():
            raise ValueError('Imported seller.company is required')
        address = seller.get('address_lines')
        if not isinstance(address, list) or not address or any(not isinstance(line, str) or not line.strip() for line in address):
            raise ValueError('Imported seller.address_lines is required')
        return
    profile = SELLER_PROFILES[template_id]
    company=clean(seller.get('company',''))
    if company and company.casefold()!=profile['company'].casefold():
        raise ValueError('Seller company differs from exact reference template; use another approved seller template')
    if seller.get('address_lines'):
        expected=profile['address_lines']
        supplied=[clean(x) for x in seller['address_lines']]
        if supplied != expected and supplied != profile.get('source_address_lines'):
            raise ValueError('seller.address_lines differs from the original seller letterhead')
    for k in ['tel', 'sales_name', 'email', 'store_name']:
        value=clean(seller.get(k,''))
        if value and value.casefold()!=clean(profile.get(k)).casefold():
            raise ValueError(f'seller.{k} differs from the source template, which has fixed business letterhead')


def fill_imported_seller(page, seller):
    regions = [(10, 76, 580, 108), (10, 108, 580, 158), (380, 183, 580, 205),
               (445, 261, 558, 279), (384, 295, 560, 378)]
    for region in regions:
        page.add_redact_annot(fitz.Rect(region), fill=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    draw_centered_lines(page, seller['company'], 14, 580, 77, 108, font=FONT_SANS, ideal=22, minimum=14)
    address = '\n'.join(seller['address_lines'])
    # The address region is replaced wholesale; restore its fixed template label.
    header, size, leading = fit_lines('ADD: ' + ', '.join(seller['address_lines']), FONT_SANS_BOLD, 560, 46, ideal=11, minimum=9, lead=1.15)
    for index, line in enumerate(header):
        draw_left(page, line, 14.4, 119 + index*leading, font=FONT_SANS_BOLD, size=size)
    detail, size, leading = fit_lines(address, FONT_SANS, 172, 76, ideal=10.45, minimum=9, lead=1.2)
    for index, line in enumerate(detail):
        draw_left(page, line, 386.4, 309.29 + index*leading, font=FONT_SANS, size=size)
    if clean(seller.get('tel')):
        draw_left(page, 'Tel: ' + clean(seller['tel']), 383.28, 198.05, font=FONT_SANS_BOLD, size=11, max_width=190)
    draw_left(page, seller.get('sales_name', ''), 449.28, 273.65, font=FONT_SANS, size=10.45, max_width=108)
    draw_left(page, seller.get('email', ''), 386.4, 289, font=FONT_SANS, size=9, max_width=172)


def fill_currency(page, currency):
    if currency == 'EUR':
        return
    symbols = page.search_for('€')
    if len(symbols) != 4:
        raise ValueError('Expected four original currency marks')
    for left, right in [(381.9, 460.55), (507.05, 558.9)]:
        page.add_redact_annot(fitz.Rect(left+1, 477, right-1, 494), fill=False)
    for rectangle in symbols:
        if rectangle.y0 > 600:
            page.add_redact_annot(rectangle, fill=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    for left, right in [(381.9, 460.55), (507.05, 558.9)]:
        value = '(' + currency + ')'
        width = fitz.get_text_length(value, fontname=FONT_SANS_BOLD, fontsize=10.45)
        draw_left(page, value, (left+right-width)/2, 487.97, font=FONT_SANS_BOLD, size=10.45)


def invoice_pdf(d,output):
    template_id = resolve_seller_template(d)
    profile = SELLER_PROFILES.get(template_id, SELLER_PROFILES['jiuyue'])
    template = Path(TEMPLATE) if template_id in {'jiuyue', 'imported'} else TEMPLATE.parent / profile['template']
    if not template.is_file():
        raise FileNotFoundError(f'Missing bundled original-layout template: {template}')
    validate_currency(d)
    if template_id == 'imported' and d.get('seller_confirmed') is not True:
        raise ValueError('Imported seller requires seller_confirmed')
    seller=d.get('seller') or {}
    validate_seller_against_template(seller, template_id)
    buyer=d.get('buyer') or {}
    source=fitz.open(template)
    doc=fitz.open()
    # Two original-height rows fit on A4 without shrinking any product text.
    # Copy the template's vector row and move its footer by exactly one row.
    groups = [d['items'][start:start+2] for start in range(0, len(d['items']), 2)]
    for page_index, items in enumerate(groups):
        shift = (len(items)-1) * (ROW_BOTTOM-ROW_TOP)
        if not shift:
            doc.insert_pdf(source)
            page=doc[-1]
        else:
            width, height = source[0].rect.width, source[0].rect.height
            page=doc.new_page(width=width, height=height)
            header=fitz.Rect(0, 0, width, ROW_BOTTOM)
            page.show_pdf_page(header, source, 0, clip=header)
            page.show_pdf_page(fitz.Rect(0, ROW_BOTTOM, width, ROW_BOTTOM+shift), source, 0,
                               clip=fitz.Rect(0, ROW_TOP, width, ROW_BOTTOM))
            page.show_pdf_page(fitz.Rect(0, ROW_BOTTOM+shift, width, height), source, 0,
                               clip=fitz.Rect(0, ROW_BOTTOM, width, height-shift))
        if template_id == 'imported':
            fill_imported_seller(page, seller)
        fill_currency(page, d['currency'])
        rate = Decimal(d['tax']['rate'])
        page.add_redact_annot(fitz.Rect(325, 627+shift, 558, 679+shift), fill=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        footer_rows = [('Total Amount:', 639.29+shift),
                       ('Amount excl. VAT:', 655.29+shift), (f'VAT ({rate:.0%}):', 671.29+shift)]
        for label, y in footer_rows:
            width = fitz.get_text_length(label, fontname=FONT_SANS, fontsize=9.95)
            draw_left(page, label, 492-width, y, font=FONT_SANS, size=9.95)
        # Recipient name is the only value printed after Importer/Buyer/Receiver.
        # Order buyer's "Entreprise Exemple" is NOT a name and is not printed here.
        # Keep both original labels Contact: and Company Name: with blank values.
        name=clean(buyer.get('name',''))
        if not name:
            raise ValueError('buyer.name required for Importer/Buyer/Receiver heading')
        draw_left(page,name,157.0,256.2,font=FONT_BOLD,size=12,max_width=224)
        if clean(buyer.get('vat_number')):
            draw_left(page, 'Buyer VAT/NIP: ' + clean(buyer['vat_number']), 157, 274.13,
                      font=FONT_SANS, size=10.45, max_width=224)
        draw_address(page,buyer)
        draw_left(page,buyer.get('city',''),106.9,347.2,font=FONT_BOLD,size=12,max_width=265)
        # The original mother PDF preprints France; Renhaoyuan leaves this value blank.
        # Replace only the value when needed, keeping the country label and geometry.
        country=clean(buyer.get('country',''))
        country_labels={'法国':'France','比利时':'Belgium','德国':'Germany',
                        '意大利':'Italy','西班牙':'Spain','英国':'United Kingdom','波兰':'Poland','葡萄牙':'Portugal'}
        country=country_labels.get(country,country)
        if not country:
            raise ValueError('buyer.country is required; cannot assume France')
        if country.casefold() != profile.get('printed_country', '').casefold():
            page.add_redact_annot(fitz.Rect(106.4,359.0,178.0,377.0),fill=False)
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
        for row_index, item in enumerate(items):
            row_top = ROW_TOP + row_index*(ROW_BOTTOM-ROW_TOP)
            row_bottom = row_top + ROW_BOTTOM-ROW_TOP
            draw_centered_lines(page,str(page_index*2+row_index+1),CELLS[0],CELLS[1],row_top,row_bottom,font=FONT_SERIF,ideal=12)
            # The reference Item No. is the Amazon ORDER number (not SKU): 3 centred lines.
            order_id=d['order_id']
            order_text=order_id[:8]+'\n'+order_id[8:16]+'\n'+order_id[16:]
            draw_centered_lines(page,order_text,CELLS[1],CELLS[2],row_top,row_bottom,font=FONT_SERIF,ideal=12)
            draw_centered_lines(page,item['title'],CELLS[2],CELLS[3],row_top,row_bottom,font=FONT_BOLD,ideal=12,minimum=9)
            description=clean(item.get('description')) or inferred_description(item['title'])
            draw_centered_lines(page,description,CELLS[3],CELLS[4],row_top,row_bottom,font=FONT_BOLD,ideal=12,minimum=8)
            draw_centered_lines(page,number_fmt(item['unit_price']),CELLS[4],CELLS[5],row_top,row_bottom,font=FONT_SERIF,ideal=12)
            draw_centered_lines(page,str(item['quantity']),CELLS[5],CELLS[6],row_top,row_bottom,font=FONT_SERIF,ideal=12)
            draw_centered_lines(page,number_fmt(item['line_total']),CELLS[6],CELLS[7],row_top,row_bottom,font=FONT_SERIF,ideal=12)
        price=d['order_total'] if d['order_total'] is not None else d['subtotal']
        values = [CURRENCY[d['currency']] + ' ' + number_fmt(amount)
                  for amount in (price, d['net_amount'], d['tax']['amount'])]
        face = fitz.Font(fontname=FONT_SANS)
        size = 9.95
        while size > 8 and max(face.text_length(v, fontsize=size) for v in values) > 57:
            size = max(8, size-0.25)
        for value, (_, y) in zip(values, footer_rows):
            width = face.text_length(value, fontsize=size)
            if width > 57:
                raise ValueError('Amount is too long for the invoice footer')
            insert_text(page, (550-width, y), value, FONT_SANS, size)
        if clean(d.get('origin')):
            draw_left(page,d['origin'],54.2,688.4+shift,font=FONT_SANS_BOLD,size=9.9,max_width=175)
        # The single 'Shipping fee' field shows NET shipping after a
        # documented shipping promotion, so it reconciles with Total Amount.
        shipping=d.get('shipping_net')
        if shipping is not None:
            draw_left(page,number_fmt(shipping),445.0,622.0+shift,font=FONT_SANS,size=9.9,max_width=70)
        if len(groups) > 1:
            draw_left(page, f'Page {page_index+1}/{len(groups)}', 496.0, 716.0+shift, font=FONT_SANS, size=8.5)
    doc.set_metadata({'title':f'COMMERCIAL INVOICE {d["order_id"]}', 'author':'Chenyu Commercial Invoice'})
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    doc.save(str(output),garbage=4,deflate=True)
    doc.close()
    source.close()


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
    p.add_argument('--template', help='Approved seller template: jiuyue, renhaoyuan or confirmed imported')
    p.add_argument('--invoice-date',help='Optional confirmation of purchase date YYYY-MM-DD; must match purchase_date')
    p.add_argument('--output',type=Path,help='Output directory; filename is always <order_id>.pdf')
    args=p.parse_args(argv)
    try:
        payload=(json.loads(args.input.read_text(encoding='utf-8')) if args.input else
                 extract_order_text(args.text.read_text(encoding='utf-8')))
        seller=json.loads(args.seller.read_text(encoding='utf-8')) if args.seller else None
        d=normalize(payload,seller=seller,invoice_date=args.invoice_date,template=args.template)
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
