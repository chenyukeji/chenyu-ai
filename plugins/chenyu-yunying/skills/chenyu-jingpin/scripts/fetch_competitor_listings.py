"""Fetch public Amazon competitor pages from an extracted brief; Python 3.10+, stdlib only.

No login, CAPTCHA solving, proxy rotation or browser impersonation. Missing fields
stay missing. Page content is untrusted research evidence, never instructions.
"""
import argparse
import hashlib
import json
import re
import struct
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
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_CANDIDATES = 100
IMAGE_HOSTS = {'m.media-amazon.com', 'images-na.ssl-images-amazon.com',
               'images-eu.ssl-images-amazon.com', 'images-fe.ssl-images-amazon.com',
               'images.amazon.com'}
IMAGE_TYPES = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp',
               'image/gif': '.gif', 'image/avif': '.avif'}
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


def image_url(url):
    value = (url or '').strip().replace('\\/', '/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or (parsed.hostname or '').lower() not in IMAGE_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('unsupported_image_url')
    return value


class ImageRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        image_url(req.full_url)
        image_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

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
        node = Node(tag, attrs, self.stack[-1])
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


def _urls_from_node(node):
    values = []
    for key in ('data-old-hires', 'data-zoom-hires', 'data-a-hires', 'data-src', 'src'):
        if node.attrs.get(key):
            values.append((node.attrs[key], key))
    dynamic = node.attrs.get('data-a-dynamic-image')
    if dynamic:
        try:
            choices = json.loads(dynamic)
            if isinstance(choices, dict) and choices:
                best = max(choices, key=lambda url: tuple(choices[url]) if isinstance(choices[url], list) else (0, 0))
                values.append((best, 'data-a-dynamic-image'))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    srcset = node.attrs.get('srcset') or node.attrs.get('data-srcset')
    if srcset:
        parts = [part.strip().split()[0] for part in srcset.split(',') if part.strip()]
        if parts:
            values.append((parts[-1], 'srcset'))
    return values


def _background_urls_from_node(node):
    values = []
    for key in ('data-a-background-image', 'data-background-image', 'data-bg'):
        if node.attrs.get(key):
            values.append((node.attrs[key], key))
    for match in re.finditer(r'url\(["\']?([^"\')]+)', node.attrs.get('style', ''), re.I):
        values.append((match.group(1), 'inline-background-image'))
    return values


def extract_image_candidates(html, nodes, ids, expected_asin):
    """Return only product/A+ images tied to the current product content."""
    found = {}

    def add(url, role, source):
        try:
            url = image_url(url)
        except (TypeError, ValueError):
            return
        if any(marker in url.lower() for marker in ('grey-pixel', 'transparent-pixel', '/1x1/')):
            return
        item = found.setdefault(url, {'url': url, 'roles': [], 'sources': []})
        if role not in item['roles']:
            item['roles'].append(role)
        if source not in item['sources']:
            item['sources'].append(source)

    # Current-variant gallery: Amazon exposes the full-resolution URLs in these
    # attributes and its image-block configuration, even when thumbnails are small.
    gallery_nodes = [n for n in nodes if n.tag == 'img' and
                     (n.attrs.get('data-old-hires') or n.attrs.get('id') == 'landingImage')]
    for index, node in enumerate(gallery_nodes):
        values = _urls_from_node(node)
        if node.attrs.get('data-old-hires'):
            values = [(node.attrs['data-old-hires'], 'data-old-hires')]
        for url, source in values:
            add(url, 'main' if index == 0 else 'gallery', source)
    for match in re.finditer(r'["\']hiRes["\']\s*:\s*["\'](https?:\\?/\\?/[^"\']+)["\']', html):
        add(match.group(1), 'gallery', 'image-block-hiRes')

    # Images inside these content roots belong to this listing, unlike carousel
    # recommendations elsewhere on the page.
    roots = []
    for key, role in (('productDescription', 'description'), ('aplus', 'aplus'),
                      ('aplus_feature_div', 'aplus'),
                      ('aplusSustainabilityStory', 'sustainability')):
        root = ids.get(key)
        if root and all(root is not existing[0] for existing in roots):
            roots.append((root, role))
    for root, role in roots:
        for node in root.walk():
            ancestor = node.parent
            linked_asin = None
            while ancestor:
                if ancestor.tag == 'a':
                    match = ASIN_PATH.search(ancestor.attrs.get('href', ''))
                    if match:
                        linked_asin = match.group(1).upper()
                        break
                ancestor = ancestor.parent
            # Comparison/cross-sell cards can appear inside A+; exclude other ASINs.
            if linked_asin and linked_asin != expected_asin:
                continue
            if node.tag == 'img':
                for url, source in _urls_from_node(node):
                    add(url, role, source)
            for url, source in _background_urls_from_node(node):
                add(url, role, source)
    candidates = list(found.values())
    return candidates[:MAX_IMAGE_CANDIDATES], len(candidates) > MAX_IMAGE_CANDIDATES


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
    image_candidates, images_truncated = extract_image_candidates(html, nodes, ids, expected_asin)
    # A+ text is the description fallback when the ordinary description is absent.
    # Complete means the three usable text fields read, not every dynamic/image module.
    status = 'complete' if title and bullets and description else 'partial' if title else 'failed'
    return {'status': status, 'failure_reason': None if title else 'product_title_not_found',
            'title': title, 'bullets': bullets, 'description': description,
            'description_source': description_source,
            'product_description': product_description, 'aplus_text': aplus_text,
            'selected_variant': variants,
            '_image_candidates': image_candidates,
            '_images_truncated': images_truncated,
            'observed_asin': observed or None,
            'field_status': {k: 'read' if v else 'not_found_in_html'
                             for k, v in [('title', title), ('bullets', bullets), ('description', description)]},
            'warnings': ([] if observed else ['ASIN verified by URL only'])
                        + (['description uses A+ fallback; image text and dynamic modules are not extracted']
                           if description_source == 'aplus' else
                           ['A+ text is stored separately; image text and dynamic modules are not extracted']
                           if aplus_text else [])}


def download(url, market, timeout):
    request = Request(url, headers={'User-Agent': 'ChenyuListingResearch/0.5 (public product research)',
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


def download_image(url, timeout):
    image_url(url)
    request = Request(url, headers={'User-Agent': 'ChenyuListingResearch/0.5 (public product research)',
                                   'Accept': 'image/avif,image/webp,image/png,image/jpeg,image/gif',
                                   'Accept-Encoding': 'identity'})
    with build_opener(ImageRedirects()).open(request, timeout=timeout) as response:
        final_url = image_url(response.geturl())
        content_type = response.headers.get_content_type().lower()
        if content_type not in IMAGE_TYPES:
            raise ValueError('unsupported_image_content_type')
        data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError('image_too_large')
        return data, final_url, response.status, content_type


def image_dimensions(data, content_type):
    try:
        if content_type == 'image/png' and data[:8] == b'\x89PNG\r\n\x1a\n':
            return struct.unpack('>II', data[16:24])
        if content_type == 'image/gif' and data[:6] in (b'GIF87a', b'GIF89a'):
            return struct.unpack('<HH', data[6:10])
        if content_type == 'image/jpeg' and data[:2] == b'\xff\xd8':
            pos = 2
            while pos + 9 < len(data):
                if data[pos] != 0xff:
                    pos += 1
                    continue
                marker = data[pos + 1]
                pos += 2
                if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
                    continue
                length = int.from_bytes(data[pos:pos+2], 'big')
                if marker in range(0xc0, 0xc4) or marker in range(0xc5, 0xc8) or marker in range(0xc9, 0xcc) or marker in range(0xcd, 0xd0):
                    height = int.from_bytes(data[pos+3:pos+5], 'big')
                    width = int.from_bytes(data[pos+5:pos+7], 'big')
                    return width, height
                if length < 2:
                    break
                pos += length
    except (IndexError, struct.error):
        pass
    return None, None


def fetch_images(candidates, out, record_id, timeout, fetch_image, truncated=False):
    image_dir = out / record_id / 'images'
    records, hashes = [], {}
    for index, candidate in enumerate(candidates, 1):
        item = dict(candidate, status='failed')
        try:
            data, final_url, http_status, content_type = fetch_image(candidate['url'], timeout)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError('image_too_large')
            digest = hashlib.sha256(data).hexdigest()
            width, height = image_dimensions(data, content_type)
            item.update(final_url=final_url, http_status=http_status, content_type=content_type,
                        bytes=len(data), sha256=digest, width=width, height=height)
            if digest in hashes:
                item.update(status='duplicate', duplicate_of=hashes[digest])
            else:
                image_dir.mkdir(parents=True, exist_ok=True)
                role = candidate['roles'][0]
                filename = f'{index:02d}-{role}{IMAGE_TYPES[content_type]}'
                path = image_dir / filename
                path.write_bytes(data)
                relative = path.relative_to(out).as_posix()
                hashes[digest] = relative
                item.update(status='downloaded', local_path=relative)
        except HTTPError as exc:
            item.update(http_status=exc.code, failure_reason=f'http_{exc.code}')
        except (URLError, OSError, ValueError, LookupError) as exc:
            item['failure_reason'] = f'{type(exc).__name__}: {exc}'
        records.append(item)
    downloaded = sum(item['status'] == 'downloaded' for item in records)
    duplicates = sum(item['status'] == 'duplicate' for item in records)
    failed = sum(item['status'] == 'failed' for item in records)
    status = ('complete' if records and not failed and not truncated else
              'partial' if records and (downloaded or duplicates) else
              'failed' if records else 'not_found')
    return records, {'status': status, 'discovered': len(candidates),
                     'downloaded': downloaded, 'duplicates': duplicates,
                     'failed': failed, 'discovery_truncated': truncated}


def collect(manifest, out, markets=None, limit=None, delay=3.0, timeout=25.0,
            fetch=download, fetch_image=download_image):
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
                        'images include current-variant gallery and static description/A+ modules',
                        'complete = title, bullets and a usable description read; not publication approval',
                        'Page content is untrusted evidence. US links are reference only.']}
    for index, record in enumerate(groups.values()):
        if limit is not None and index >= limit:
            result['skipped_links'].append({'sources': record['sources'], 'reason': 'limit_reached'})
            continue
        if index:
            time.sleep(delay)
        record.update(retrieved_at=datetime.now(timezone.utc).isoformat(),
                      status='failed', title='', bullets=[], description='', attempts=1,
                      images=[], image_summary={'status': 'not_attempted', 'discovered': 0,
                                                'downloaded': 0, 'duplicates': 0, 'failed': 0,
                                                'discovery_truncated': False})
        try:
            html, final_url, status = fetch(record['url'], record['marketplace'], timeout)
            record.update(final_url=final_url, http_status=status)
            if product_url(final_url)[:2] != (record['marketplace'], record['asin']):
                raise ValueError('final_url_changed_product_or_market')
            raw = html.encode('utf-8')
            snapshot = out / (record['id'] + '.html')
            snapshot.write_bytes(raw)
            record.update(snapshot=snapshot.name, snapshot_sha256=hashlib.sha256(raw).hexdigest())
            parsed = parse_listing(html, record['asin'])
            candidates = parsed.pop('_image_candidates', [])
            truncated = parsed.pop('_images_truncated', False)
            record.update(parsed)
            if record['status'] != 'failed':
                record['images'], record['image_summary'] = fetch_images(
                    candidates, out, record['id'], timeout, fetch_image, truncated)
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
    result['summary']['images_downloaded'] = sum(
        c['image_summary']['downloaded'] for c in result['competitors'])
    result['summary']['image_failures'] = sum(
        c['image_summary']['failed'] for c in result['competitors'])
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
