import base64
import importlib.util
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest


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
history = load_module("chenyu_new_releases_history", "scripts/new_releases_history.py")


def build_history_database(path, with_identity=False):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE observations (
            source_url TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            category TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            asin TEXT NOT NULL,
            title TEXT NOT NULL,
            review_count INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            price_text TEXT NOT NULL DEFAULT '',
            rating REAL NOT NULL DEFAULT 0,
            product_url TEXT NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (source_url, snapshot_date, asin)
        )
        """
    )
    rows = [
        ("2026-09-01", 30, "B0HISTORY1", "Birthday Balloon Kit"),
        ("2026-09-02", 20, "B0HISTORY1", "Birthday Balloon Kit"),
        ("2026-09-03", 10, "B0HISTORY1", "Birthday Balloon Kit"),
        ("2026-09-02", 5, "B0HISTORY2", "Blue Balloon Set"),
        ("2026-09-03", 6, "B0HISTORY2", "Blue Balloon Set"),
        ("2026-09-03", 2, "B0HISTORY3", "Party Sticker Pack"),
    ]
    connection.executemany(
        """
        INSERT INTO observations (
            source_url, marketplace, category, snapshot_date, rank, asin, title,
            review_count, price, price_text, rating, product_url, image_url
        ) VALUES (?, 'US', 'party-supplies', ?, ?, ?, ?, 4, 9.99, '$9.99', 4.5, ?, ?)
        """,
        [
            (
                "https://amazon.example/new-releases/party",
                snapshot_date,
                rank,
                asin,
                title,
                f"https://www.amazon.com/dp/{asin}",
                f"https://images.example/{'group-a' if asin in {'B0HISTORY1', 'B0HISTORY2'} else asin}.jpg",
            )
            for snapshot_date, rank, asin, title in rows
        ],
    )
    if with_identity:
        connection.execute(
            """
            CREATE TABLE product_seen (
                marketplace TEXT NOT NULL,
                asin TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                product_url TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (marketplace, asin)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO product_seen (
                marketplace, asin, first_seen, last_seen, title, product_url, image_url
            ) VALUES ('US', ?, ?, '2026-09-03', '', '', '')
            """,
            [
                ("B0HISTORY1", "2026-08-20"),
                ("B0HISTORY2", "2026-09-02"),
                ("B0HISTORY3", "2026-09-03"),
            ],
        )
    connection.commit()
    connection.close()


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


def test_amazon_identity_records_keep_image_and_product_link_fallbacks():
    rows = [
        {
            "marketplace": "US",
            "asin": "B0IMAGE001",
            "new_release_rank": 1,
            "product_name": "Untrusted source title",
            "price": 9.99,
            "image_url": "https://images-na.ssl-images-amazon.com/images/I/example.jpg",
            "detail_url": "https://www.amazon.com/dp/B0IMAGE001",
        }
    ]
    result = run._identity_only(rows, "US", 20)
    assert result[0]["image_url"].endswith("example.jpg")
    assert result[0]["detail_url"].endswith("B0IMAGE001")
    assert "product_name" not in result[0]
    assert "price" not in result[0]


def test_scoring_is_descending_and_explains_reasons():
    candidates = pipeline.merge_candidates(fixture_records())
    result = pipeline.score_candidates(candidates, shortlist_limit=1, as_of_date="2026-09-20")
    assert result["results"][0]["primary_listing"]["asin"] == "B0HIGH0001"
    assert result["results"][0]["score"] > result["results"][1]["score"]
    assert result["results"][0]["screening_status"] == "SHORTLISTED"
    assert "新品榜第3名" in result["results"][0]["reason"]
    assert result["results"][0]["reason_version"] == "decision_reason_v2"
    assert all(
        label in result["results"][0]["decision_reason"]
        for label in ("市场信号：", "竞争门槛：", "新品与价格：", "销售周期：", "主要风险：", "数据与评分：", "下一步：")
    )
    assert result["results"][1]["screening_status"] == "REVIEW_LATER"


def test_conclusion_caps_conflicting_risk_and_missing_data_signals():
    assert pipeline._conclusion(95, [], rank=5, sales=500, reviews=500) == "🟢 条件开"
    assert pipeline._conclusion(95, [], rank=5, sales=500, reviews=150) == "🟢 开"
    assert pipeline._conclusion(95, ["售价"], rank=5, sales=500, reviews=10) == "🟡 待补数据"
    assert pipeline._conclusion(95, ["售价", "Review数量"], rank=5, sales=500, reviews=None) == "🟡 待补数据"
    assert pipeline._conclusion(95, [], rank=5, sales=20, reviews=10) == "🟡 偏弱"


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


def test_workbook_fetches_each_unique_image_once_and_reuses_embedded_images(tmp_path):
    scored = pipeline.score_candidates(pipeline.merge_candidates(fixture_records()), as_of_date="2026-09-20")
    rows = pipeline.table_rows(scored)
    for row in rows:
        row["图片"] = "https://images.example/shared-product.png"
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z1ZsAAAAASUVORK5CYII="
    )
    calls = []

    def first_loader(url):
        calls.append(url)
        return one_pixel_png, "png"

    output = tmp_path / "开品结果.xlsx"
    first = workbook.export_discovery_workbook(output, rows, image_loader=first_loader)
    assert calls == ["https://images.example/shared-product.png"]
    assert first["embedded_image_count"] == 2
    assert first["unique_image_fetch_count"] == 1
    assert first["downloaded_image_count"] == 2

    def should_not_fetch(_):
        raise AssertionError("existing embedded images should be copied from the workbook")

    second = workbook.export_discovery_workbook(output, rows, image_loader=should_not_fetch)
    assert second["embedded_image_count"] == 2
    assert second["reused_image_count"] == 2
    assert second["downloaded_image_count"] == 0
    assert second["unique_image_fetch_count"] == 0


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
        assert payload["query_timeout_ms"] == 8000
        assert payload["query_delay_ms"] == 200
        assert payload["query_poll_ms"] == 200
        assert payload["empty_grace_ms"] == 800
        return {
            "collection_status": "complete",
            "source_metadata": {"marketplace": "US", "selected_market": "美国站"},
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
    assert raw["query_metadata"][0]["selected_market"] == "美国站"


def test_sellersprite_resume_skips_cached_unavailable_asins(monkeypatch, tmp_path):
    source = {
        "marketplace": "DE",
        "asin": "B0UNAVAIL1",
        "new_release_rank": 8,
        "source_strategy": "E",
    }
    calls = []

    def fake_enrich(payload):
        calls.append(payload["asins"])
        return {
            "collection_status": "partial",
            "records": [],
            "outcomes": [
                {"asin": "B0UNAVAIL1", "status": "not_found", "record_count": 0, "stop_reason": "confirmed_empty", "empty_verified": True, "auth_verified": True, "observed_at": run._now()}
            ],
        }

    monkeypatch.setattr(run, "collect_sellersprite_by_asin", fake_enrich)
    run_dir = tmp_path / "negative-cache-run"
    run_dir.mkdir()
    payload = {"discovery": {"sellersprite_enrich": True}}

    first_manifest = {"artifacts": {}, "warnings": []}
    run._enrich_records_from_sellersprite([source], payload, run_dir, first_manifest)
    assert calls == [["B0UNAVAIL1"]]

    second_manifest = {"artifacts": {}, "warnings": []}
    run._enrich_records_from_sellersprite([source], payload, run_dir, second_manifest)
    assert calls == [["B0UNAVAIL1"]]
    raw = json.loads((run_dir / "05-sellersprite-de-raw.json").read_text(encoding="utf-8"))
    assert raw["counts"]["queried"] == 0
    assert raw["counts"]["skipped_cached_unavailable"] == 1


def test_new_releases_database_answers_daily_repeat_similarity_and_rising_questions(tmp_path):
    db_path = tmp_path / "new_releases.db"
    build_history_database(db_path)
    result = history.analyze_new_releases_database(
        {
            "db_path": str(db_path),
            "marketplaces": ["US"],
            "category": "party-supplies",
            "as_of_date": "2026-09-03",
            "days": 3,
            "limit": 20,
            "history": {
                "min_repeat_days": 2,
                "min_rank_improvement": 5,
                "min_rising_consistency": 0.6,
                "min_group_asins": 2,
            },
        }
    )
    report = result["marketplaces"]["US"]
    assert report["today"]["count"] == 3
    assert report["yesterday"]["count"] == 2
    assert report["first_appearances"]["today_count"] == 1
    assert {row["asin"] for row in report["continuous_products"]["products"]} == {
        "B0HISTORY1",
        "B0HISTORY2",
    }
    group = report["similar_product_groups"]["groups"][0]
    assert group["recent_member_count"] == 2
    assert set(group["member_asins"]) == {"B0HISTORY1", "B0HISTORY2"}
    assert group["pair_evidence"][0]["image_similarity"] == 1.0
    assert group["pair_evidence"][0]["title_similarity"] > 0
    assert [row["asin"] for row in report["rising_products"]["products"]] == ["B0HISTORY1"]
    assert report["rising_products"]["products"][0]["rank_history"] == [
        {"date": "2026-09-01", "rank": 30},
        {"date": "2026-09-02", "rank": 20},
        {"date": "2026-09-03", "rank": 10},
    ]
    assert report["date_basis"]["first_seen_basis"] == "earliest_retained_observation"
    assert any("product_seen" in warning for warning in report["warnings"])


def test_unmatched_titles_are_not_forced_into_similarity_groups(tmp_path):
    db_path = tmp_path / "new_releases.db"
    build_history_database(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        UPDATE observations SET title = CASE asin
            WHEN 'B0HISTORY1' THEN 'Wooden Maze Board'
            WHEN 'B0HISTORY2' THEN 'Silicone Baking Mold'
            ELSE 'Fabric Storage Basket'
        END
        """
    )
    connection.commit()
    connection.close()

    result = history.analyze_new_releases_database(
        {
            "db_path": str(db_path),
            "marketplaces": ["US"],
            "as_of_date": "2026-09-03",
            "days": 3,
            "history": {"min_group_asins": 2},
        }
    )
    groups = result["marketplaces"]["US"]["similar_product_groups"]
    assert groups["status"] == "INSUFFICIENT_IMAGE_EVIDENCE"
    assert groups["image_comparable_pairs"] == 0
    assert groups["count"] == 0
    assert any("没有可同时比较标题和主图" in warning for warning in result["warnings"])


def test_visual_difference_blocks_group_even_when_titles_match(tmp_path):
    from PIL import Image

    db_path = tmp_path / "new_releases.db"
    build_history_database(db_path)
    left_path = tmp_path / "left.png"
    right_path = tmp_path / "right.png"
    left = Image.new("L", (9, 8))
    right = Image.new("L", (9, 8))
    left.putdata([column * 28 for _row in range(8) for column in range(9)])
    right.putdata([(8 - column) * 28 for _row in range(8) for column in range(9)])
    left.save(left_path)
    right.save(right_path)

    connection = sqlite3.connect(db_path)
    connection.execute(
        "UPDATE observations SET title = 'Matching Party Product', image_url = ? WHERE asin = 'B0HISTORY1'",
        (left_path.as_uri(),),
    )
    connection.execute(
        "UPDATE observations SET title = 'Matching Party Product', image_url = ? WHERE asin = 'B0HISTORY2'",
        (right_path.as_uri(),),
    )
    connection.commit()
    connection.close()

    result = history.analyze_new_releases_database(
        {
            "db_path": str(db_path),
            "marketplaces": ["US"],
            "as_of_date": "2026-09-03",
            "days": 3,
            "history": {"min_group_asins": 2},
        }
    )
    groups = result["marketplaces"]["US"]["similar_product_groups"]
    assert groups["status"] == "NO_SIMILAR_PRODUCT_GROUPS"
    assert groups["image_comparable_pairs"] >= 1
    assert groups["count"] == 0


def test_database_schema_has_no_type_or_label_column_and_similarity_still_groups(tmp_path):
    db_path = tmp_path / "new_releases.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE observations (
            source_url TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            category TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            asin TEXT NOT NULL,
            title TEXT NOT NULL,
            image_url TEXT NOT NULL,
            PRIMARY KEY (source_url, snapshot_date, asin)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE product_seen (
            marketplace TEXT NOT NULL,
            asin TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY (marketplace, asin)
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO observations VALUES (
            'https://amazon.example/new-releases/party', 'US', 'party-supplies',
            '2026-09-03', ?, ?, ?, 'https://images.example/group-a.jpg'
        )
        """,
        [(1, "B0NO_TYPE1", "Birthday Balloon Kit"), (2, "B0NO_TYPE2", "Blue Balloon Set")],
    )
    connection.executemany(
        "INSERT INTO product_seen VALUES ('US', ?, '2026-09-03', '2026-09-03')",
        [("B0NO_TYPE1",), ("B0NO_TYPE2",)],
    )
    connection.commit()
    connection.close()

    result = history.analyze_new_releases_database(
        {"db_path": str(db_path), "marketplaces": ["US"], "as_of_date": "2026-09-03"}
    )
    report = result["marketplaces"]["US"]
    assert report["today"]["count"] == 2
    assert report["similar_product_groups"]["status"] == "AVAILABLE"
    group = report["similar_product_groups"]["groups"][0]
    assert group["recent_member_count"] == 2
    assert set(group["member_asins"]) == {"B0NO_TYPE1", "B0NO_TYPE2"}


def test_database_schema_requires_main_image_for_similarity_analysis(tmp_path):
    db_path = tmp_path / "new_releases.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE observations (
            source_url TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            category TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            rank INTEGER NOT NULL,
            asin TEXT NOT NULL,
            title TEXT NOT NULL,
            PRIMARY KEY (source_url, snapshot_date, asin)
        )
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(history.HistoryDatabaseError, match="image_url"):
        history.analyze_new_releases_database(
            {"db_path": str(db_path), "marketplaces": ["US"], "as_of_date": "2026-09-03"}
        )


def test_new_releases_database_prefers_identity_table_and_builds_discovery_seeds(tmp_path):
    db_path = tmp_path / "new_releases.db"
    build_history_database(db_path, with_identity=True)
    result = run.handle(
        {
            "skill_action": "analyze_new_releases_db",
            "db_path": str(db_path),
            "marketplaces": ["US"],
            "as_of_date": "2026-09-03",
            "days": 3,
            "limit": 20,
            "history": {"min_repeat_days": 2, "min_group_asins": 2},
        }
    )
    report = result["marketplaces"]["US"]
    assert report["date_basis"]["first_seen_basis"] == "product_seen"
    assert {row["asin"] for row in report["first_appearances"]["window"]} == {
        "B0HISTORY2",
        "B0HISTORY3",
    }
    records = history.discovery_records_from_history(result, limit=20)
    first = records[0]
    assert first["asin"] == "B0HISTORY1"
    assert set(first["history_signals"]) == {"REPEAT", "RISING"}
    assert first["history_consecutive_snapshots"] == 3
    candidates = pipeline.merge_candidates(records)
    scored = pipeline.score_candidates(candidates, as_of_date="2026-09-03")
    rising_scored = next(
        row for row in scored["results"] if row["primary_listing"]["asin"] == "B0HISTORY1"
    )
    assert "窗口排名净提升20名" in rising_scored["decision_reason"]


def test_discovery_flow_can_use_history_database_instead_of_live_amazon(monkeypatch, tmp_path):
    db_path = tmp_path / "new_releases.db"
    build_history_database(db_path, with_identity=True)

    def fake_workbook(path, rows):
        return {"path": str(path), "row_count": len(rows), "embedded_image_count": 0}

    monkeypatch.setattr(run, "export_discovery_workbook", fake_workbook)
    run_dir = tmp_path / "history-run"
    result = run.handle(
        {
            "skill_action": "run_discovery_flow",
            "request": "从历史新品榜找最近持续出现和排名上升的派对用品",
            "strategy_selection": {"strategy_ids": ["E"], "source_marketplaces": ["US"]},
            "run_dir": str(run_dir),
            "as_of_date": "2026-09-03",
            "discovery": {
                "source": "new_releases_db",
                "history_db_path": str(db_path),
                "db_category": "party-supplies",
                "history_days": 3,
                "history": {"min_repeat_days": 2, "min_group_asins": 2},
                "sellersprite_enrich": False,
            },
        }
    )
    assert result["status"] == "PARTIAL"
    assert result["counts"]["source_records"] == 3
    assert Path(result["artifacts"]["new_releases_history"]).exists()
    source = json.loads((run_dir / "07-source-records.json").read_text(encoding="utf-8"))
    assert any("RISING" in row.get("history_signals", []) for row in source["records"])


def test_status_exposes_one_focused_skill_workflow():
    status = run.handle({"skill_action": "status"})
    assert status["skill"] == "chenyu-xuanpin"
    assert status["purpose"] == "选品、分析评分并生成开品表格"
    assert "run_discovery_flow" in status["actions"]
    assert "enrich_sellersprite" in status["actions"]
    assert "analyze_new_releases_db" in status["actions"]
    assert all("supply" not in action and "economics" not in action for action in status["actions"])
