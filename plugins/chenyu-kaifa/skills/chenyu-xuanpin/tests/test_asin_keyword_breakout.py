import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from asin_keyword_breakout import normalize_item, render


class ReverseKeywordReportTests(unittest.TestCase):
    def test_monthly_points_and_matching_product_are_rendered(self):
        item = normalize_item({
            "keywords": "brotbeutel bienenwachs", "keywordCn": "面包袋蜂蜡",
            "searches": 16740, "searchesGrowth": 16.23, "exactPpc": 0.97,
            "purchases": 71, "latest7daysAds": 189, "products": 412,
            "searchesTrend": [{"month": month, "searches": searches} for month, searches in
                              [("202606", 0), ("202607", 120), ("202608", 8000), ("202609", 16740)]],
        })
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new("RGB", (80, 80), "#e0b36d").save(root / "product.png")
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "marketplace": "DE", "asin": "B0HJ66GXZK",
                "product": {"name": "Bienenwachs Brotbeutel", "url": "https://www.amazon.de/dp/B0HJ66GXZK",
                            "image_file": "product.png"},
                "source_url": "https://www.sellersprite.com/v3/keyword-reverse/?q=B0HJ66GXZK",
                "observed_at": "2026-10-19T00:00:00+00:00", "collected_count": 174,
                "reported_total": 174, "keywords": [item],
            }), encoding="utf-8")
            selected = root / "selected.json"
            selected.write_text(json.dumps([{"marketplace": "DE", "asin": "B0HJ66GXZK",
                                             "keyword": "brotbeutel bienenwachs",
                                             "direction": "蜂蜡面包袋"}]), encoding="utf-8")
            result = render([evidence], selected, root / "report")
            workbook = load_workbook(result["workbook"])
            sheet = workbook["长尾词趋势"]
            self.assertEqual(sheet["C2"].value, "brotbeutel bienenwachs")
            self.assertEqual(sheet["F2"].value, 16740)
            self.assertEqual(sheet["N2"].value, "B0HJ66GXZK")
            self.assertEqual(len(sheet._images), 2)
            monthly = workbook["逐月搜索量原始点"]
            self.assertEqual(monthly.max_row, 5)
            self.assertEqual(monthly["D5"].value, "202609")
            self.assertEqual(monthly["E5"].value, 16740)
            workbook.close()
            with Image.open(result["preview"]) as preview:
                self.assertEqual(preview.size, (1600, 205))

    def test_unverified_keyword_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "marketplace": "DE", "asin": "B0HJ66GXZK", "product": {"name": "Bread Bag"},
                "source_url": "source", "observed_at": "today", "collected_count": 0,
                "reported_total": 0, "keywords": [],
            }))
            selection = root / "selection.json"
            selection.write_text(json.dumps([{"marketplace": "DE", "asin": "B0HJ66GXZK",
                                              "keyword": "invented term"}]))
            with self.assertRaisesRegex(ValueError, "反查证据没有关键词"):
                render([evidence], selection, root / "out")


if __name__ == "__main__":
    unittest.main()
