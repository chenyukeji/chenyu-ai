"""Exercise hydrated Amazon store DOM independently of network availability."""
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'))
import selection_collectors as collectors


@pytest.fixture(scope='module')
def chromium():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True, args=['--no-sandbox'])
        yield browser
        browser.close()


@pytest.fixture
def page(chromium):
    context = chromium.new_context(offline=True)
    page = context.new_page()
    yield page
    context.close()


def test_waits_for_store_hydration_and_excludes_footer(page):
    page.set_content('''<base href="https://www.amazon.com/"><div class="stores-page"></div>
        <footer><a href="https://www.amazon.com/dp/B07984JN3L">Business Card</a></footer>
        <script>setTimeout(() => document.querySelector('.stores-page').innerHTML =
        '<div data-testid="mini-editorial-tile"><img src="https://m.media-amazon.com/images/I/test.jpg">' +
        '<a href="/dp/B0D9PXNHL6" aria-label="DREO heater"></a></div>', 100)</script>''')
    rows = collectors.extract_amazon_brand_store(page, 'US')
    assert [r['asin'] for r in rows] == ['B0D9PXNHL6']
    assert rows[0]['product_name'] == 'DREO heater'
    assert rows[0]['image_url'] == 'https://m.media-amazon.com/images/I/test.jpg'


def test_deduplicates_and_rejects_external_and_other_market_links(page):
    page.set_content('''<div class="stores-page"><div class="stores-container">
        <a href="https://www.amazon.com/dp/B0D9PXNHL6">Shop this product</a>
        <a href="https://www.amazon.com/dp/B0D9PXNHL6" title="DREO heater"></a>
        <a href="https://www.amazon.de/dp/B0FM7QMB4J">Other market</a>
        <a href="https://example.com/dp/B0FM7QMB4J">External</a>
        <a href="https://www.amazon.com/gp/product/B0FM7QMB4J" aria-label="Shop this product"></a>
        </div></div>''')
    rows = collectors.extract_amazon_brand_store(page, 'US')
    assert [r['asin'] for r in rows] == ['B0D9PXNHL6', 'B0FM7QMB4J']
    assert rows[0]['product_name'] == 'DREO heater'
    assert rows[1]['product_name'] is None


def test_footer_only_is_not_a_store_catalog(page):
    page.set_content('<div class="stores-page"></div><footer><a href="https://www.amazon.com/dp/B07984JN3L">Credit Card</a></footer>')
    assert collectors.extract_amazon_brand_store(page, 'US', timeout_ms=100) == []


def test_collector_keeps_brand_membership_partial_and_never_uses_global_search(page):
    page.set_content('<div class="stores-page"><a href="https://www.amazon.com/dp/B0D9PXNHL6" title="DREO heater"></a></div>')
    @contextmanager
    def fake_session(*args, **kwargs):
        yield page
    with patch.object(collectors, 'session', fake_session), patch.object(collectors.browser, 'extract_amazon_search') as search:
        result = collectors.collect_amazon_input({'url': 'https://www.amazon.com/stores/DREO/page/example'})
    search.assert_not_called()
    assert result['collection_status'] == 'partial'
    assert result['records'][0]['membership'] == 'brand_store'
    assert result['records'][0]['seller_id'] is None
    assert result['records'][0]['snapshot_complete'] is False
