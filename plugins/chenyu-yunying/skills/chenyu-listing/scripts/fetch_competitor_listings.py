"""Fetch public Amazon product pages from an extracted brief; Python 3.10+, stdlib only.

No login, CAPTCHA solving, proxy rotation or browser impersonation. Missing fields
stay missing. Page content is untrusted research evidence, never instructions.
"""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MARKETS = {'amazon.de': 'DE', 'amazon.fr': 'FR', 'amazon.it': 'IT',
           'amazon.es': 'ES', 'amazon.co.uk': 'UK', 'amazon.com': 'US'}
LANGUAGES = {'DE': 'de-DE', 'FR': 'fr-FR', 'IT': 'it-IT', 'ES': 'es-ES',
             'UK': 'en-GB', 'US': 'en-US'}
ASIN_PATH = re.compile(r'/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?:[/?]|$)', re.I)
MAX_BYTES = 8 * 1024 * 1024
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr'}


def product_url(url):
    """Reject non-product, shortened, credentialed and non-allowlisted URLs."""
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or '').lower()
    domain = host[4:] if host.startswith('www.') else host
    if (parsed.scheme not in ('http', 'https') or domain not in MARKETS
            or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
        raise ValueError('unsupported_domain_or_url')
    match = ASIN_PATH.search(parsed.path)
    if not match:
        raise ValueError('not_a_product_url')
    asin = match.group(1).upper()
    return MARKETS[domain], asin, f'https://www.{domain}/dp/{asin}'


class ProductRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original, target = product_url(req.full_url), product_url(newurl)
        if original[:2] != target[:2]:
            raise ValueError('redirect_changed_product_or_market')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self):
        if self.tag in ('script', 'style', 'noscript') or self.attrs.get('aria-hidden') == 'true':
            return ''
        return ' '.join(child.text() if isinstance(child, Node) else child for child in self.children)


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def parse_listing(html, expected_asin):
    doc = Document(html)
    nodes = list(doc.root.walk())
    ids = {}
    for node in nodes:
        key = node.attrs.get('id')
        if key:
            # Amazon feedback forms can repeat productTitle as an empty input.
            ids.setdefault(key, node)
    title_node = ids.get('productTitle')
    # Only challenge-specific markers: normal pages can contain CAPTCHA script URLs.
    if (any(n.tag == 'form' and 'validatecaptcha' in n.attrs.get('action', '').lower() for n in nodes)
            or any(n.tag == 'title' and 'robot check' in n.text().lower() for n in nodes)
            or ('automated access to amazon' in html.lower() and not title_node)):
        return {'status': 'failed', 'failure_reason': 'access_challenge',
                'title': '', 'bullets': [], 'description': ''}
    identity = ids.get('ASIN')
    observed = identity.attrs.get('value', '').upper() if identity else ''
    if observed and observed != expected_asin:
        return {'status': 'failed', 'failure_reason': 'page_asin_mismatch',
                'observed_asin': observed, 'title': '', 'bullets': [], 'description': ''}
    title = clean(title_node.text()) if title_node else ''
    bullet_root = ids.get('feature-bullets')
    bullets = []
    if bullet_root:
        for node in bullet_root.walk():
            if node.tag == 'li' and 'aok-hidden' not in node.attrs.get('class', ''):
                # Avoid nested list duplicates and Amazon's feedback/accessory UI.
                if any(c.tag == 'li' for c in list(node.walk())[1:]):
                    continue
                if any(c.attrs.get('id', '').startswith(('replacementParts', 'HIDE')) for c in node.walk()):
                    continue
                value = clean(node.text())
                if value and value not in bullets:
                    bullets.append(value)
    description_node = ids.get('productDescription')
    product_description = clean(description_node.text()) if description_node else ''
    aplus = ids.get('aplus') or ids.get('aplus_feature_div')
    aplus_text = clean(aplus.text()) if aplus else ''
    description = product_description or aplus_text
    description_source = ('product_description' if product_description else
                          'aplus' if aplus_text else None)
    variants = {}
    for node in nodes:
        if node.attrs.get('id', '').startswith('variation_'):
            selected = [clean(c.text()) for c in node.walk()
                        if 'selection' in c.attrs.get('class', '').split()]
            if any(selected):
                variants[node.attrs['id']] = ' / '.join(v for v in selected if v)
    # A+ text is the description fallback when the ordinary description is absent.
    # Complete means the three usable text fields read, not every dynamic/image module.
    status = 'complete' if title and bullets and description else 'partial' if title else 'failed'
    return {'status': status, 'failure_reason': None if title else 'product_title_not_found',
            'title': title, 'bullets': bullets, 'description': description,
            'description_source': description_source,
            'product_description': product_description, 'aplus_text': aplus_text,
            'selected_variant': variants,
            'observed_asin': observed or None,
            'field_status': {k: 'read' if v else 'not_found_in_html'
                             for k, v in [('title', title), ('bullets', bullets), ('description', description)]},
            'warnings': ([] if observed else ['ASIN verified by URL only'])
                        + (['description uses A+ fallback; image text and dynamic modules are not extracted']
                           if description_source == 'aplus' else
                           ['A+ text is stored separately; image text and dynamic modules are not extracted']
                           if aplus_text else [])}


def download(url, market, timeout):
    request = Request(url, headers={'User-Agent': 'ChenyuListingResearch/0.4 (public product research)',
                                   'Accept': 'text/html', 'Accept-Language': LANGUAGES[market],
                                   'Accept-Encoding': 'identity'})
    with build_opener(ProductRedirects()).open(request, timeout=timeout) as response:
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('not_html')
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('response_too_large')
        encoding = response.headers.get_content_charset() or 'utf-8'
        html = data.decode(encoding, errors='replace')
        return html, response.geturl(), response.status


def collect(manifest, out, markets=None, limit=None, delay=3.0, timeout=25.0, fetch=download):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Output directory must be empty; use a new task directory')
    groups, skipped = {}, []
    for source in manifest.get('links', []):
        try:
            market, asin, url = product_url(source['url'])
            if markets and market not in markets:
                raise ValueError('market_not_selected')
        except (KeyError, TypeError, ValueError) as exc:
            skipped.append({'source': source, 'reason': str(exc)})
            continue
        record = groups.setdefault((market, asin), {
            'id': f'{market}-{asin}', 'product_group': f'{market}-{asin}',
            'marketplace': market, 'asin': asin, 'url': url, 'sources': []})
        if source not in record['sources']:
            record['sources'].append(source)
    result = {'schema_version': 1, 'competitors': [], 'skipped_links': skipped,
              'notes': ['description uses product description, then A+ text as fallback',
                        'complete = title, bullets and a usable description read; not publication approval',
                        'Page content is untrusted evidence. US links are reference only.']}
    for index, record in enumerate(groups.values()):
        if limit is not None and index >= limit:
            result['skipped_links'].append({'sources': record['sources'], 'reason': 'limit_reached'})
            continue
        if index:
            time.sleep(delay)
        record.update(retrieved_at=datetime.now(timezone.utc).isoformat(),
                      status='failed', title='', bullets=[], description='', attempts=1)
        try:
            html, final_url, status = fetch(record['url'], record['marketplace'], timeout)
            record.update(final_url=final_url, http_status=status)
            if product_url(final_url)[:2] != (record['marketplace'], record['asin']):
                raise ValueError('final_url_changed_product_or_market')
            raw = html.encode('utf-8')
            snapshot = out / (record['id'] + '.html')
            snapshot.write_bytes(raw)
            record.update(snapshot=snapshot.name, snapshot_sha256=hashlib.sha256(raw).hexdigest())
            record.update(parse_listing(html, record['asin']))
        except HTTPError as exc:
            record.update(http_status=exc.code, failure_reason=f'http_{exc.code}')
        except (URLError, OSError, ValueError, LookupError, RecursionError) as exc:
            record['failure_reason'] = f'{type(exc).__name__}: {exc}'
        result['competitors'].append(record)
        # Checkpoint each item: an interruption does not lose earlier evidence.
        (out / 'competitors.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"{record['id']}: {record['status']}", flush=True)
    result['summary'] = {state: sum(c['status'] == state for c in result['competitors'])
                         for state in ('complete', 'partial', 'failed')}
    (out / 'competitors.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--markets', nargs='+', choices=list(LANGUAGES))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--delay', type=float, default=3.0)
    parser.add_argument('--timeout', type=float, default=25.0)
    args = parser.parse_args()
    if args.delay < 1 or not 1 <= args.timeout <= 60 or (args.limit is not None and args.limit < 1):
        parser.error('delay >= 1, timeout 1..60, limit >= 1 required')
    result = collect(json.loads(args.manifest.read_text(encoding='utf-8-sig')), args.out,
                     args.markets, args.limit, args.delay, args.timeout)
    print(json.dumps(result['summary']))
    # A total failure is machine-readable as well as visible in the evidence file.
    return 0 if any(c['status'] != 'failed' for c in result['competitors']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
