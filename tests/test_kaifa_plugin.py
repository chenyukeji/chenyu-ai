import base64
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/chenyu-kaifa/skills/chenyu-xuanpin"
SCRIPTS = SKILL / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, SKILL / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run = load_module("chenyu_xuanpin_run", "scripts/run.py")
pipeline = load_module("chenyu_discovery_pipeline", "scripts/discovery_pipeline.py")
workbook = load_module("chenyu_discovery_workbook", "scripts/discovery_workbook.py")
router = load_module("chenyu_strategy_router", "scripts/strategy_router.py")
collector = load_module("chenyu_playwright_collector", "scripts/playwright_collector.py")


def fixture_records():
    return [
        {
            "marketplace": "DE",
            "asin": "B0HIGH0001",
            "product_name": "Party Balloon Arch Kit",
            "new_release_rank": 3,
            "price": 14.99,
            "currency": "EUR",
            "estimated_sales": 520,
            "review_count": 18,
            "source_available_date": "2026-09-05",
            "bsr": 842,
            "category_name": "Party Supplies",
            "detail_url": "https://www.amazon.de/dp/B0HIGH0001",
            "source_strategy": "E",
            "source_ref": "https://www.amazon.de/gp/new-releases#rank=3",
        },
        {
            "marketplace": "US",
            "asin": "B0LOW00002",
            "product_name": "Birthday Table Cover",
            "new_release_rank": 88,
            "price": 28.0,
            "currency": "USD",
            "estimated_sales": 20,
            "review_count": 450,
            "source_available_date": "2025-01-01",
            "bsr": 62000,
            "category_name": "Party Supplies",
            "detail_url": "https://www.amazon.com/dp/B0LOW00002",
            "source_strategy": "E",
            "source_ref": "https://www.amazon.com/gp/new-releases#rank=88",
        },
    ]


def test_numeric_ten_character_amazon_asin_is_supported():
    assert collector._extract_asin("ASIN: 1690299274") == "1690299274"
    assert collector._extract_asin("https://www.amazon.com/dp/1690299274") == "1690299274"


def test_default_request_uses_strategy_e_and_us_de():
    task = run.create_task("开发一批派对用品")
    resolution = task["strategy_resolution"]
    assert resolution["strategy_ids"] == ["E"]
    assert resolution["selection_source"] == "default"
    assert resolution["source_marketplaces"] == ["US", "DE"]


def test_request_can_infer_multiple_strategies():
    task = run.create_task("从新品榜找最近60天的FBM派对用品")
    assert task["strategy_resolution"]["strategy_ids"] == ["E", "J"]
    assert task["strategy_resolution"]["selection_source"] == "inferred"


def test_explicit_strategy_overrides_language_inference():
    task = run.create_task(
        "从新品榜找产品",
        strategy_selection={"strategy_ids": ["C"], "source_marketplaces": ["DE"]},
    )
    assert task["strategy_resolution"]["strategy_ids"] == ["C"]
    assert task["strategy_resolution"]["source_marketplaces"] == ["DE"]
    assert task["strategy_resolution"]["selection_source"] == "explicit"


def test_party_supplies_resolves_us_and_de_new_release_nodes():
    task = run.create_task("针对玩具类目的派对用品找新品")
    category = task["category_resolution"]
    assert category["status"] == "resolved"
    assert set(category["amazon_new_releases"]) == {"US", "DE"}


def test_candidates_do_not_merge_across_marketplaces_by_title():
    rows = fixture_records()
    rows[1]["product_name"] = rows[0]["product_name"]
    rows[1]["asin"] = rows[0]["asin"]
    candidates = pipeline.merge_candidates(rows)
    assert len(candidates) == 2


def test_scoring_is_descending_and_explains_reasons():
    candidates = pipeline.merge_candidates(fixture_records())
    result = pipeline.score_candidates(candidates, shortlist_limit=1, as_of_date="2026-09-20")
    assert result["results"][0]["primary_listing"]["asin"] == "B0HIGH0001"
    assert result["results"][0]["score"] > result["results"][1]["score"]
    assert result["results"][0]["screening_status"] == "SHORTLISTED"
    assert "新品榜第3名" in result["results"][0]["reason"]
    assert result["results"][1]["screening_status"] == "REVIEW_LATER"


def test_missing_metrics_are_named_instead_of_treated_as_zero():
    candidates = pipeline.merge_candidates(
        [{"marketplace": "DE", "asin": "B0MISSING1", "new_release_rank": 5, "source_strategy": "E"}]
    )
    result = pipeline.score_candidates(candidates, as_of_date="2026-09-20")
    row = result["results"][0]
    assert "预估月销量" in row["reason"]
    assert "Review数量" in row["reason"]
    assert "预估月销量" in row["missing_data"]
    assert row["score_components"]["预估月销量"] == 0


def test_table_rows_match_requested_columns():
    scored = pipeline.score_candidates(pipeline.merge_candidates(fixture_records()), as_of_date="2026-09-20")
    rows = pipeline.table_rows(scored)
    assert rows[0]["得分"] >= rows[1]["得分"]
    assert rows[0]["结论"]
    assert rows[0]["理由"]
    assert rows[0]["亚马逊产品链接"].endswith("B0HIGH0001")
    assert "缺" not in rows[0]["缺点"]
    assert "全年可售" in rows[0]["生命周期"]
    assert not re.search(r"[A-Za-z]", rows[0]["产品优点&特征"])
    assert "开品建议" not in rows[0]


def test_lifecycle_means_saleable_months_and_disadvantages_are_product_specific():
    records = fixture_records()
    records[0]["product_name"] = "Halloween Latex Balloon Party Kit"
    scored = pipeline.score_candidates(pipeline.merge_candidates(records), as_of_date="2026-09-20")
    row = pipeline.table_rows(scored)[0]
    assert row["生命周期"] == "8–10月（万圣节季）"
    assert "破损" in row["缺点"] or "漏气" in row["缺点"]
    assert "新品期" not in row["生命周期"]


def test_workbook_has_reference_columns_and_sorted_scores(tmp_path):
    scored = pipeline.score_candidates(pipeline.merge_candidates(fixture_records()), as_of_date="2026-09-20")
    rows = list(reversed(pipeline.table_rows(scored)))
    output = tmp_path / "开品结果.xlsx"
    rows[0]["图片"] = "https://images.example/product.png"
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z1ZsAAAAASUVORK5CYII="
    )
    result = workbook.export_discovery_workbook(output, rows, image_loader=lambda _: (one_pixel_png, "png"))
    assert result["row_count"] == 2
    assert result["embedded_image_count"] == 1
    with zipfile.ZipFile(output) as package:
        sheet_bytes = package.read("xl/worksheets/sheet1.xml")
        sheet = ET.fromstring(sheet_bytes)
        workbook_xml = ET.fromstring(package.read("xl/workbook.xml"))
        names = set(package.namelist())
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert workbook_xml.find("s:sheets/s:sheet", ns).attrib["name"] == "开品结果"
    assert sheet.find("s:autoFilter", ns).attrib["ref"] == "A1:O3"
    conclusion = sheet.find(".//s:c[@r='N2']/s:is/s:t", ns)
    assert conclusion.text in {"🟢 强开", "🟢 开", "🟢 条件开", "🟡 偏弱", "🟡 观察", "🔴 不建议"}
    assert "xl/drawings/drawing1.xml" in names
    assert "xl/media/image1.png" in names
    assert b"IMAGE(" not in sheet_bytes


def test_end_to_end_inline_discovery_creates_ranked_workbook(tmp_path):
    result = run.handle(
        {
            "skill_action": "run_discovery_flow",
            "request": "针对玩具类目的派对用品找新品",
            "task": {"task_id": "party-fixture", "shortlist_limit": 1},
            "run_dir": str(tmp_path / "run"),
            "discovery_records": fixture_records(),
            "discovery": {"sellersprite_enrich": False},
            "as_of_date": "2026-09-20",
        }
    )
    assert result["status"] == "COMPLETE"
    assert result["strategy_resolution"]["strategy_ids"] == ["E"]
    assert result["counts"]["candidates"] == 2
    assert Path(result["workbook"]["path"]).exists()
    manifest = json.loads((tmp_path / "run/00-run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"


def test_sellersprite_enrichment_backfills_missing_product_metrics(monkeypatch, tmp_path):
    source = {
        "marketplace": "US",
        "asin": "B0ENRICH01",
        "new_release_rank": 2,
        "source_strategy": "E",
    }

    def fake_enrich(payload):
        assert payload["marketplace"] == "US"
        assert payload["asins"] == ["B0ENRICH01"]
        return {
            "collection_status": "complete",
            "records": [
                {
                    "marketplace": "US",
                    "asin": "B0ENRICH01",
                    "product_name": "Birthday Party Favor Set",
                    "source_available_date": "2026-09-10",
                    "review_count": 12,
                    "price": 15.99,
                    "currency": "USD",
                    "bsr": 1234,
                    "estimated_sales": 260,
                }
            ],
        }

    monkeypatch.setattr(run, "collect_sellersprite_by_asin", fake_enrich)
    run_dir = tmp_path / "enrichment-run"
    result = run.handle(
        {
            "skill_action": "run_discovery_flow",
            "request": "找派对用品新品",
            "run_dir": str(run_dir),
            "discovery_records": [source],
            "discovery": {"sellersprite_enrich": True},
            "as_of_date": "2026-09-20",
        }
    )
    assert result["status"] == "COMPLETE"
    row = json.loads((run_dir / "10-table-rows.json").read_text(encoding="utf-8"))["rows"][0]
    assert row["上架日期"] == "2026-09-10"
    assert row["大品类排名"] == 1234
    assert row["所在品类"] == "玩具 > 派对用品"
    assert row["预估月销量"] == 260
    raw = json.loads((run_dir / "05-sellersprite-us-raw.json").read_text(encoding="utf-8"))
    assert raw["counts"]["enriched"] == 1


def test_status_exposes_one_focused_skill_workflow():
    status = run.handle({"skill_action": "status"})
    assert status["skill"] == "chenyu-xuanpin"
    assert status["purpose"] == "选品、分析评分并生成开品表格"
    assert "run_discovery_flow" in status["actions"]
    assert "enrich_sellersprite" in status["actions"]
    assert all("supply" not in action and "economics" not in action for action in status["actions"])
