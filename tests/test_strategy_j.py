"""J strategy: independent SellerSprite source, strict eligibility and evidence limits."""
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts"
sys.path.insert(0, str(SCRIPTS))

import run
import sellersprite_j
from strategy_j import qualify_recent_fbm, score_recent_fbm


def row(asin, *, days="2026-09-10", fulfillment="FBM", sales=500, price=10,
        category="Kitchen", variants=2, title="Kitchen tool"):
    return {
        "marketplace": "US", "asin": asin, "source_available_date": days,
        "fulfillment": fulfillment, "estimated_sales": sales, "price": price,
        "currency": "USD", "category_name": category, "variation_count": variants,
        "review_count": 15, "product_name": title,
    }


def test_j_rejects_old_fba_low_sales_and_unknown_dates():
    records = [
        row("B0JGOOD001"),
        row("B0JOLD0001", days="2026-06-01"),
        row("B0JFBA0001", fulfillment="FBA"),
        row("B0JLOW0001", sales=20),
        row("B0JNODATE1", days=None),
    ]
    result = qualify_recent_fbm(records, as_of_date="2026-09-26")
    assert [item["asin"] for item in result["accepted"]] == ["B0JGOOD001"]
    assert result["counts"] == {"examined": 5, "qualified": 1, "rejected": 4}
    assert "fulfillment_not_verified_fbm" in result["rejected"][1]["reasons"] or any(
        "fulfillment_not_verified_fbm" in item["reasons"] for item in result["rejected"]
    )


def test_j_explains_price_variants_and_marks_unobserved_causes_unknown():
    records = [
        row("B0JGOOD001", price=10, variants=24, title="Halloween Kitchen Tool"),
        row("B0JPEER001", price=20),
        row("B0JPEER002", price=22),
        row("B0JPEER003", price=24),
    ]
    qualified = qualify_recent_fbm(records, as_of_date="2026-09-26")["accepted"]
    scored = score_recent_fbm(qualified, records, as_of_date="2026-09-26")
    first = next(item for item in scored["results"] if item["primary_listing"]["asin"] == "B0JGOOD001")
    factors = {item["factor"]: item for item in first["factor_evidence"]}
    assert factors["低价"]["status"] == "observed"
    assert factors["超多变体"]["status"] == "observed"
    assert factors["季节性"]["status"] == "hypothesis"
    assert factors["站外流量"]["status"] == "unverified"
    assert factors["功能创新"]["status"] == "unverified"
    assert "因果关系尚未证实" in first["reason"]


def test_j_flow_uses_product_research_without_new_releases(monkeypatch, tmp_path):
    sample = [
        row("B0JGOOD001", price=10, variants=24),
        row("B0JPEER001", price=20),
        row("B0JPEER002", price=22),
    ]
    def fake_research(payload):
        assert payload["marketplace"] == "US"
        return {"collection_status": "complete", "records": sample,
                "source_metadata": {"filters": {"listing_age_days": 60, "fulfillment": "FBM"}}}
    monkeypatch.setattr(run, "collect_recent_fbm", fake_research)
    monkeypatch.setattr(run, "_live_strategy_e", lambda *args: (_ for _ in ()).throw(
        AssertionError("J must not call Amazon New Releases")
    ))
    output = tmp_path / "out" / "开品结果.xlsx"
    result = run.handle({
        "skill_action": "run_discovery_flow",
        "request": "近60天 FBM 机会",
        "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
        "run_dir": str(tmp_path / "internal"),
        "output_path": str(output),
        "as_of_date": "2026-09-26",
    })
    assert result["status"] == "COMPLETE"
    assert result["counts"]["qualified"] == 3
    assert output.exists()
    with zipfile.ZipFile(output) as package:
        sheet = ET.fromstring(package.read("xl/worksheets/sheet1.xml"))
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert sheet.find("s:autoFilter", ns).attrib["ref"] == "A1:R4"
    text = "".join(node.text or "" for node in sheet.findall(".//s:t", ns))
    assert "近期火爆原因" in text
    assert "站外流量" in text
    manifest = json.loads((tmp_path / "internal" / "00-run.json").read_text())
    assert manifest["status"] == "COMPLETE"


def test_recent_fbm_new_product_words_choose_j_without_new_release_source():
    task = run.create_task("找近60天 FBM 新品")
    assert task["strategy_resolution"]["strategy_ids"] == ["J"]
    assert run.handle({"skill_action": "list_strategies"})["strategies"][-1]["implementation_status"] == "available"


def test_j_refreshes_when_research_filters_change(monkeypatch, tmp_path):
    calls = []
    def fake_research(payload):
        calls.append(payload["keyword"])
        return {"collection_status": "complete", "records": [row("B0JGOOD001")]}
    monkeypatch.setattr(run, "collect_recent_fbm", fake_research)
    base = {
        "skill_action": "run_discovery_flow",
        "request": "近60天 FBM 机会",
        "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
        "run_dir": str(tmp_path / "internal"),
        "output_path": str(tmp_path / "out" / "开品结果.xlsx"),
        "as_of_date": "2026-09-26",
    }
    run.handle({**base, "discovery": {"j_keyword": "kitchen"}})
    run.handle({**base, "discovery": {"j_keyword": "garden"}})
    assert calls == ["kitchen", "garden"]


def test_j_delivers_verified_site_when_other_site_is_blocked(monkeypatch, tmp_path):
    def fake_research(payload):
        if payload["marketplace"] == "DE":
            return {"collection_status": "blocked", "block_reason": "login_required",
                    "records": []}
        return {"collection_status": "complete", "records": [row("B0JGOOD001")]}
    monkeypatch.setattr(run, "collect_recent_fbm", fake_research)
    result = run.handle({
        "skill_action": "run_discovery_flow", "request": "近60天 FBM 机会",
        "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US", "DE"]},
        "run_dir": str(tmp_path / "internal"),
        "output_path": str(tmp_path / "out" / "开品结果.xlsx"),
        "as_of_date": "2026-09-26",
    })
    assert result["status"] == "PARTIAL"
    assert result["counts"]["qualified"] == 1
    assert (tmp_path / "out" / "开品结果.xlsx").exists()
    assert any("DE" in warning for warning in result["warnings"])


def test_j_collection_failure_keeps_blocking_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "collect_recent_fbm", lambda payload: (_ for _ in ()).throw(
        RuntimeError("filter control changed")
    ))
    result = run.handle({
        "skill_action": "run_discovery_flow", "request": "近60天 FBM 机会",
        "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
        "run_dir": str(tmp_path / "internal"),
    })
    assert result["status"] == "AWAITING_ENRICHMENT"
    assert "j_product_research_RuntimeError" in result["blocking_items"][0]
    assert Path(result["artifacts"]["sellersprite_j_us"]).exists()



def test_j_attempts_environment_login_before_searching_when_session_is_guest():
    page = MagicMock()
    context = MagicMock()
    runtime = MagicMock()
    manager = MagicMock()
    manager.__enter__.return_value = runtime
    with patch.object(sellersprite_j, "_sellersprite_credentials",
                      return_value=("test-account", "test-secret", "environment")), \
         patch.object(sellersprite_j, "_require_playwright", return_value=lambda: manager), \
         patch.object(sellersprite_j, "_launch_context",
                      return_value=(context, page, Path("/tmp/test-profile"))), \
         patch.object(sellersprite_j, "_goto"), \
         patch.object(sellersprite_j, "_challenge_visible", return_value=False), \
         patch.object(sellersprite_j, "_wait_for_sellersprite_identity", return_value="guest"), \
         patch.object(sellersprite_j, "_login_sellersprite_in_page",
                      return_value={"login_status": "blocked",
                                    "block_reason": "sellersprite_security_challenge_requires_user"}) as login:
        result = sellersprite_j.collect_recent_fbm({"marketplace": "US"})
    assert result["collection_status"] == "blocked"
    assert result["block_reason"] == "sellersprite_security_challenge_requires_user"
    assert result["records"] == []
    assert login.call_args.kwargs["require_asin_query"] is False
    page.get_by_text.assert_not_called()
    assert "test-secret" not in str(result)


def test_j_recollects_partial_cache_after_login_becomes_available(monkeypatch, tmp_path):
    calls = []
    def fake_research(payload):
        calls.append(payload["marketplace"])
        return {"collection_status": "partial" if len(calls) == 1 else "complete",
                "records": [row("B0JGOOD001")]}
    monkeypatch.setattr(run, "collect_recent_fbm", fake_research)
    payload = {
        "skill_action": "run_discovery_flow",
        "request": "近60天 FBM 机会",
        "strategy_selection": {"strategy_ids": ["J"], "source_marketplaces": ["US"]},
        "run_dir": str(tmp_path / "internal"),
        "output_path": str(tmp_path / "out" / "开品结果.xlsx"),
        "as_of_date": "2026-09-26",
    }
    first = run.handle(payload)
    second = run.handle(payload)
    assert first["status"] == "PARTIAL"
    assert second["status"] == "COMPLETE"
    assert calls == ["US", "US"]
