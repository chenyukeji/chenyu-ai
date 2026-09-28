import json
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run


class StrategyJAITests(unittest.TestCase):
    def test_ai_analysis_required_and_category_is_marked_when_inferred(self):
        with tempfile.TemporaryDirectory() as folder:
            args = {
                "request": "近60天 FBM 选品",
                "run_dir": folder,
                "task": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
                "as_of_date": "2026-09-27",
                "discovery": {"j_enrich_details": False},
                "discovery_records": [{
                    "marketplace": "US", "asin": "B0HCBQ5SDF",
                    "source_available_date": "2026-09-20",
                    "fulfillment": "FBM", "estimated_sales": 2300,
                    "product_name": "Halloween pumpkin decoration kit",
                    "price": 19.99, "currency": "USD", "review_count": 12,
                    "variation_count": 5,
                }],
            }
            pending = run.run_discovery_flow(args)
            self.assertEqual(pending["status"], "AWAITING_AI_ANALYSIS")
            self.assertFalse(Path(folder, "开品结果.xlsx").exists())
            self.assertEqual(pending["analysis_requests"][0]["asin"], "B0HCBQ5SDF")
            analysis = (
                "上架仅7天已有预估月销2300件且评论12条，显示近期需求值得继续调查。"
                "标题指向万圣节装饰场景，节日需求可能推动购买，但仅凭标题无法确认季节销量趋势。"
                "先核对历史销量与同类竞品，再判断是否适合开品。"
            )
            complete = run.run_discovery_flow({
                "run_dir": folder,
                "as_of_date": "2026-09-27",
                "discovery": {"j_enrich_details": False},
                "j_ai_analyses": [{
                    "marketplace": "US", "asin": "B0HCBQ5SDF",
                    "category_name": "节日装饰用品",
                    "analysis": analysis,
                }],
            })
            self.assertEqual(complete["status"], "COMPLETE")
            workbook = Path(complete["workbook"]["path"])
            with zipfile.ZipFile(workbook) as archive:
                root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
            texts = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            self.assertIn("所在品类", texts)
            self.assertIn("AI分析", texts)
            self.assertNotIn("近期火爆原因", texts)
            self.assertNotIn("理由", texts)
            self.assertIn("AI推断：节日装饰用品", texts)
            self.assertIn(analysis, texts)
            self.assertNotIn("产品优点&特征", texts)
            self.assertNotIn("缺点", texts)
            self.assertNotIn("待验证", " ".join(texts))

    def test_collector_preserves_explicit_category_column(self):
        import playwright_collector as collector
        table = {
            "tableIndex": 0,
            "headers": ["产品信息", "所在品类", "上架时间", "配送方式", "月销量"],
            "rows": [{
                "cells": ["Garden planter B0HCBQ5SDF", "Garden & Outdoor",
                          "2026-09-20", "FBM", "400"],
                "links": ["https://www.amazon.de/dp/B0HCBQ5SDF"],
                "imageUrls": [],
            }],
        }
        page = MagicMock()
        page.url = "https://www.sellersprite.com/v3/product-research"
        with patch.object(collector, "_extract_best_table", return_value=table):
            records = collector.extract_sellersprite_table(page, {"marketplace": "DE"})
        self.assertEqual(records[0]["category_name"], "Garden & Outdoor")

    def test_product_detail_bullets_enter_ai_evidence(self):
        from strategy_j import qualify_recent_fbm, score_recent_fbm, ai_analysis_requests
        source = [{
            "marketplace": "US", "asin": "B0HCBQ5SDF",
            "source_available_date": "2026-09-20", "fulfillment": "FBM",
            "estimated_sales": 400, "product_name": "Garden planter",
        }]
        qualified = qualify_recent_fbm(source, as_of_date="2026-09-27")["accepted"]
        screening = score_recent_fbm(qualified, source, as_of_date="2026-09-27")
        detail = {
            "collection_status": "complete",
            "records": [{
                "marketplace": "US", "asin": "B0HCBQ5SDF",
                "feature_bullets": ["Drainage holes reduce standing water"],
                "source_ref": "https://www.amazon.com/dp/B0HCBQ5SDF",
            }],
        }
        with tempfile.TemporaryDirectory() as folder, patch.object(run, "collect", return_value=detail) as collect:
            manifest = {"artifacts": {}, "warnings": []}
            run._enrich_j_shortlist_details(screening, {}, Path(folder), manifest)
            collect.assert_called_once()
            request = ai_analysis_requests(screening)[0]
            self.assertEqual(request["feature_bullets"], ["Drainage holes reduce standing water"])
            self.assertEqual(request["detail_source_ref"], "https://www.amazon.com/dp/B0HCBQ5SDF")

    def test_pending_language_is_rejected(self):
        from strategy_j import qualify_recent_fbm, score_recent_fbm, apply_ai_analyses
        source = [{
            "marketplace": "US", "asin": "B0HCBQ5SDF",
            "source_available_date": "2026-09-20", "fulfillment": "FBM",
            "estimated_sales": 400, "category_name": "Garden",
        }]
        screening = score_recent_fbm(
            qualify_recent_fbm(source, as_of_date="2026-09-27")["accepted"],
            source, as_of_date="2026-09-27",
        )
        with self.assertRaisesRegex(ValueError, "without 待验证"):
            apply_ai_analyses(screening, [{
                "marketplace": "US", "asin": "B0HCBQ5SDF",
                "analysis": "上架七天，预估月销四百件。产品缺点待验证，先检查趋势和同类商品价格。",
            }])

    def test_j_image_anchor_and_reuse_follow_shifted_columns(self):
        from discovery_workbook import export_discovery_workbook, _embedded_images_by_product
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        )
        rows = [{
            "站点": "US", "ASIN": "B0HCBQ5SDF",
            "图片": "https://example.com/product.png",
            "AI分析": "标题显示庭院花盆，详情有排水孔；上架七天预估月销四百件，可继续比较同类售价。",
            "得分": 60,
        }]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "j.xlsx"
            export_discovery_workbook(path, rows, image_loader=lambda url: (png, "png"))
            self.assertIn(("US", "B0HCBQ5SDF"), _embedded_images_by_product(path))
            with zipfile.ZipFile(path) as archive:
                drawing = ET.fromstring(archive.read("xl/drawings/drawing1.xml"))
            ns = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
            self.assertEqual(drawing.find(f".//{ns}from/{ns}col").text, "10")
            reused = export_discovery_workbook(
                path, rows, image_loader=lambda url: self.fail("image redownloaded"),
            )
            self.assertEqual(reused["reused_image_count"], 1)

    def test_source_category_overrides_ai_inference(self):
        from strategy_j import qualify_recent_fbm, score_recent_fbm, apply_ai_analyses, table_rows_recent_fbm
        source = [{
            "marketplace": "DE", "asin": "B0HCBQ5SDF",
            "source_available_date": "2026-09-20", "fulfillment": "FBM",
            "estimated_sales": 400, "category_name": "Garten",
            "product_name": "Garden planter",
        }]
        qualified = qualify_recent_fbm(source, as_of_date="2026-09-27")["accepted"]
        screening = score_recent_fbm(qualified, source, as_of_date="2026-09-27")
        pending = apply_ai_analyses(screening, [{
            "marketplace": "DE", "asin": "B0HCBQ5SDF",
            "category_name": "错误的推断",
            "analysis": "标题显示庭院种植盆，适合小空间种植；上架7天预估月销400件，可比较同类售价和后续销量。",
        }])
        self.assertEqual(pending, [])
        self.assertEqual(table_rows_recent_fbm(screening)[0]["所在品类"], "Garten")


if __name__ == "__main__":
    unittest.main()
