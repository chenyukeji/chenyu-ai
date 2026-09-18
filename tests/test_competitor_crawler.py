import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-yunying/skills/chenyu-listing/scripts/fetch_competitor_listings.py'
spec = importlib.util.spec_from_file_location('crawler', SCRIPT)
crawler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crawler)

PAGE = '''<html><head><title>Product</title></head><body>
<input id="ASIN" value="B012345678"><span id="productTitle">Étoile &amp; fête</span>
<div id="feature-bullets"><ul><li><span>Papier <b>doré</b></span></li>
<li>Décoration</li><li class="aok-hidden">Hidden</li></ul></div>
<div id="productDescription"><p>Pour la fête.</p><script>ignore()</script></div>
<div id="variation_color_name"><span class="selection">Or</span></div>
<div id="aplus"><p>Extra information</p></div>
<form><input id="productTitle" value=""></form></body></html>'''


class CrawlerTests(unittest.TestCase):
    def test_parse_fields_and_variants(self):
        result = crawler.parse_listing(PAGE, 'B012345678')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['title'], 'Étoile & fête')
        self.assertEqual(result['bullets'], ['Papier doré', 'Décoration'])
        self.assertEqual(result['description'], 'Pour la fête.')
        self.assertEqual(result['selected_variant']['variation_color_name'], 'Or')
        self.assertEqual(result['aplus_text'], 'Extra information')

    def test_failures_and_partial(self):
        self.assertEqual(crawler.parse_listing('<title>Robot Check</title>', 'B012345678')['failure_reason'], 'access_challenge')
        self.assertEqual(crawler.parse_listing(PAGE, 'B087654321')['failure_reason'], 'page_asin_mismatch')
        partial = crawler.parse_listing('<span id="productTitle">Title</span>', 'B012345678')
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['field_status']['description'], 'not_found_in_html')
        self.assertEqual(crawler.parse_listing('<title>Sign in</title>', 'B012345678')['status'], 'failed')

    def test_urls(self):
        self.assertEqual(crawler.product_url('https://www.amazon.de/name/dp/B012345678/ref=x?th=1'),
                         ('DE', 'B012345678', 'https://www.amazon.de/dp/B012345678'))
        for url in ['https://amazon.de.evil.test/dp/B012345678', 'file:///etc/passwd',
                    'https://localhost/dp/B012345678', 'https://amazon.de/s?k=tree',
                    'https://user@amazon.de/dp/B012345678', 'https://amazon.de:8888/dp/B012345678']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                crawler.product_url(url)
        with self.assertRaises(ValueError):
            crawler.ProductRedirects().redirect_request(Request('https://amazon.de/dp/B012345678'),
                                                       None, 302, '', {}, 'https://amazon.fr/dp/B012345678')

    def test_dedup_snapshots_and_analyzer_contract(self):
        links = [{'url': 'https://amazon.fr/dp/B012345678?th=1', 'cell': 'A1'},
                 {'url': 'https://www.amazon.fr/dp/B012345678', 'cell': 'A2'},
                 {'url': 'https://amazon.de/dp/B012345678', 'cell': 'A3'},
                 {'url': 'https://example.com/supplier'}]
        calls = []
        def fetch(url, market, timeout):
            calls.append(url)
            return PAGE, url, 200
        with tempfile.TemporaryDirectory() as tmp:
            result = crawler.collect({'links': links}, tmp, delay=0, fetch=fetch)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(result['competitors'][0]['sources']), 2)
            self.assertEqual(len(result['skipped_links']), 1)
            self.assertEqual(result['summary']['complete'], 2)
            self.assertTrue((Path(tmp) / result['competitors'][0]['snapshot']).exists())
            self.assertEqual(json.loads((Path(tmp) / 'competitors.json').read_text(encoding='utf-8')), result)
            with self.assertRaises(ValueError):
                crawler.collect({'links': links}, tmp, fetch=fetch)

    def test_http_failure_continues_and_limit(self):
        def fetch(url, market, timeout):
            raise HTTPError(url, 503, 'Unavailable', {}, None)
        links = [{'url': 'https://amazon.de/dp/B012345678'}, {'url': 'https://amazon.fr/dp/B012345678'}]
        with tempfile.TemporaryDirectory() as tmp:
            result = crawler.collect({'links': links}, tmp, limit=1, delay=0, fetch=fetch)
            self.assertEqual(result['competitors'][0]['failure_reason'], 'http_503')
            self.assertEqual(result['summary']['failed'], 1)
            self.assertEqual(result['skipped_links'][0]['reason'], 'limit_reached')


if __name__ == '__main__':
    unittest.main()
