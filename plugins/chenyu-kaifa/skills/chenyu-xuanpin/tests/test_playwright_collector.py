from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase, mock
from urllib.parse import parse_qs, urlparse


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "playwright_collector.py"
SPEC = importlib.util.spec_from_file_location("chenyu_playwright_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class FakePage:
    def __init__(self):
        self.url = "https://www.sellersprite.com/v3/competitor-lookup?monthName=bsr_sales_nearly"
        self.waits = []

    def wait_for_timeout(self, milliseconds):
        self.waits.append(milliseconds)


class SellerSpriteBatchTests(TestCase):
    def test_batch_url_preserves_existing_query_and_encodes_asins(self):
        url = collector._sellersprite_batch_url(
            "https://www.sellersprite.com/v3/competitor-lookup?monthName=bsr_sales_nearly",
            "US",
            ["B012345678", "B0ABCDEFGHI"],
            60,
        )

        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["monthName"], ["bsr_sales_nearly"])
        self.assertEqual(query["market"], ["US"])
        self.assertEqual(query["asins"], ['["B012345678","B0ABCDEFGHI"]'])
        self.assertEqual(query["page"], ["1"])
        self.assertEqual(query["size"], ["60"])

    def test_batch_query_returns_all_requested_rows_without_single_fallback(self):
        page = FakePage()
        requested = ["B012345678", "B0ABCDEFGHI"]
        rows = [{"asin": asin, "product_name": asin} for asin in requested]

        def fake_goto(target_page, url):
            target_page.url = url

        with (
            mock.patch.object(collector, "_SellerSpriteQueryResponse") as observer,
            mock.patch.object(collector, "_sellersprite_auth_state", return_value="authenticated"),
            mock.patch.object(collector, "_goto", side_effect=fake_goto),
            mock.patch.object(collector, "_challenge_visible", return_value=False),
            mock.patch.object(collector, "extract_sellersprite_table", return_value=rows),
        ):
            observer.return_value.completed = True
            observer.return_value.empty = False
            observer.return_value.error = None
            records, elapsed_ms, reason = collector._query_sellersprite_batch(
                page,
                {},
                "US",
                requested,
                query_timeout_ms=8000,
                query_poll_ms=200,
                empty_grace_ms=800,
            )

        self.assertEqual({row["asin"] for row in records}, set(requested))
        self.assertGreaterEqual(elapsed_ms, 0)
        self.assertEqual(reason, "matched")
        self.assertEqual(page.waits, [])

    def test_amazon_product_extracts_primary_image(self):
        page = mock.MagicMock()
        page.url = "https://www.amazon.com/dp/B012345678"
        page.locator.return_value.get_attribute.return_value = "B012345678"
        page.locator.return_value.all_inner_texts.return_value = []

        def fake_attribute(_page, _selectors, attribute):
            return "https://images-na.ssl-images-amazon.com/images/I/product.jpg" if attribute == "data-old-hires" else None

        with (
            mock.patch.object(collector, "_first_text", return_value=None),
            mock.patch.object(collector, "_first_attribute", side_effect=fake_attribute),
        ):
            record = collector.extract_amazon_product(page, {"marketplace": "US"})[0]

        self.assertEqual(record["asin"], "B012345678")
        self.assertEqual(
            record["image_url"],
            "https://images-na.ssl-images-amazon.com/images/I/product.jpg",
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
