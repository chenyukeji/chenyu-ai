import importlib.util
import json
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "chenyu-kaifa"


def load_module(name, relpath):
    path = PLUGIN / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


kaifa = load_module("chenyu_kaifa_run", "skills/chenyu-kaifa/scripts/run.py")
jihui = load_module("chenyu_jihui_run", "skills/chenyu-jihui/scripts/run.py")
pingshen = load_module("chenyu_kaifa_pingshen_run", "skills/chenyu-kaifa-pingshen/scripts/run.py")


def full_evidence(candidate_id="cand-1"):
    fields = {
        "cn_seller_evidence": 1,
        "target_market_demand": {"signal": "observed"},
        "comparable_competition": {"groups": 12},
        "comparable_price": {"min": 11.99, "max": 16.99},
        "product_specs": {"material": "silicone", "size": "10cm", "pack_count": 1},
        "review_pain_points": ["hard to clean"],
        "fulfillment_and_delivery": {"fba_presence": "observed"},
    }
    return [
        {
            "evidence_id": f"ev-{i}",
            "candidate_id": candidate_id,
            "field": field,
            "value": value,
            "evidence_status": "fact" if field != "target_market_demand" else "estimate",
            "source_type": "fixture",
            "source_ref": f"fixture:{field}",
            "source_market": "DE",
            "observed_at": "2026-09-18T12:00:00+02:00",
        }
        for i, (field, value) in enumerate(fields.items(), start=1)
    ]


def example_economics():
    return pingshen.calculate_economics(
        {
            "marketplace": "DE",
            "fulfillment_path": "FBA",
            "price_gross_eur": 15.0,
            "vat_rate": 0.19,
            "cny_per_eur": 8.0,
            "purchase_cny": 14.0,
            "packaging_cny": 2.0,
            "referral_fee_eur": 2.25,
            "fulfillment_fee_eur": 2.70,
            "inbound_eur": 0.60,
            "storage_eur": 0.30,
            "returns_reserve_eur": 0.30,
            "other_variable_eur": 0.0,
            "cpc_eur": 0.30,
            "ad_cvr": 0.10,
            "ad_order_share": 1.0,
            "ad_sales_per_order_eur": 15.0,
            "trial_units": 20,
        }
    )


def test_runtime_rules_are_identical_and_executable():
    paths = [
        PLUGIN / "skills/chenyu-kaifa/references/runtime-rules.json",
        PLUGIN / "skills/chenyu-jihui/references/runtime-rules.json",
        PLUGIN / "skills/chenyu-kaifa-pingshen/references/runtime-rules.json",
    ]
    rules = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    assert rules[0] == rules[1] == rules[2]
    assert rules[0]["plugin_name"] == "chenyu-kaifa"
    assert rules[0]["status"] == "runtime"
    assert rules[0]["sales_marketplaces"] == ["DE", "FR", "IT", "ES"]
    assert rules[0]["target_price_eur"] == {"min": 5.0, "max": 20.0, "inclusive": True}
    assert rules[0]["purchase_packaging_cap_cny"] == 20.0


def test_task_entry_applies_defaults_and_auto_routes():
    task = kaifa.create_task(
        {
            "task_id": "task-fixture",
            "category_or_need": "kitchen organization",
            "keywords": ["drawer organizer"],
            "target_season": "Q4",
        }
    )
    assert task["sales_marketplaces"] == ["DE", "FR", "IT", "ES"]
    assert task["target_price_eur"] == {"min": 5.0, "max": 20.0}
    assert task["purchase_packaging_cap_cny"] == 20.0
    assert set(["A", "E", "J", "C", "H"]).issubset(task["strategy_ids"])
    plan = kaifa.build_plan(task)
    assert [p["owner_skill"] for p in plan["phases"]] == [
        "chenyu-jihui",
        "chenyu-jihui",
        "chenyu-kaifa-pingshen",
        "chenyu-kaifa-pingshen",
    ]


def test_task_entry_rejects_relaxing_business_cap():
    with pytest.raises(kaifa.ContractError):
        kaifa.create_task({"purchase_packaging_cap_cny": 21})


def test_multi_strategy_parent_candidate_merges_without_summing_sales():
    rows = [
        {
            "marketplace": "DE",
            "asin": "CHILD-A",
            "parent_asin": "PARENT-1",
            "product_name": "Example Product",
            "source_strategy": "E",
            "source_ref": "new-release:1",
            "estimated_sales": 50,
            "sales_level": "parent",
            "observed_at": "2026-09-18T10:00:00+02:00",
        },
        {
            "marketplace": "DE",
            "asin": "CHILD-B",
            "parent_asin": "PARENT-1",
            "product_name": "Example Product Variant",
            "source_strategy": "J",
            "source_ref": "fbm:2",
            "estimated_sales": 50,
            "sales_level": "parent",
            "observed_at": "2026-09-18T10:00:00+02:00",
        },
        {
            "marketplace": "DE",
            "asin": "CHILD-A",
            "parent_asin": "PARENT-1",
            "product_name": "Example Product",
            "source_strategy": "A",
            "source_ref": "cn-seller:3",
            "estimated_sales": 50,
            "sales_level": "parent",
            "observed_at": "2026-09-18T10:00:00+02:00",
        },
    ]
    merged = jihui.merge_candidates(rows)
    assert len(merged) == 1
    candidate = merged[0]
    assert set(candidate["source_strategies"]) == {"A", "E", "J"}
    assert candidate["source_record_count"] == 3
    assert len(candidate["marketplace_listings"]) == 2
    assert candidate["sales_aggregation"]["status"] == "not_aggregated"
    assert "sales_total" not in candidate


def test_opportunity_card_preserves_pending_instead_of_inventing_values():
    candidate = {
        "candidate_id": "cand-1",
        "product_name_normalized": "Example Product",
        "source_strategies": ["E"],
        "source_refs": ["new-release:1"],
    }
    card = jihui.build_opportunity_card(candidate, full_evidence()[:2], ["DE"])
    assert card["decision_readiness"] == "partial"
    assert "product_specs" in card["pending_verification"]
    pending = card["evidence"]["product_specs"][0]
    assert pending["evidence_status"] == "pending_verification"
    assert pending["value"] is None


def test_supply_match_and_bundle_apply_20_cny_hard_gate():
    match = pingshen.match_supply(
        {
            "candidate_id": "cand-1",
            "material": "silicone",
            "size": "10cm",
            "pack_count": 1,
        },
        {
            "supplier": "fixture",
            "supplier_sku": "SKU-1",
            "material": "Silicone",
            "size": "10cm",
            "pack_count": 1,
            "unit_quote_cny": 14,
            "packaging_cny": 2,
            "sample_status": "passed",
        },
    )
    assert match["match_type"] == "exact"
    assert match["cost_gate"]["status"] == "pass"
    assert match["cost_gate"]["total_cny"] == 16

    bundle = pingshen.build_bundle(
        [
            {"supplier_sku": "A", "unit_quote_cny": 11, "quantity": 1},
            {"supplier_sku": "B", "unit_quote_cny": 8, "quantity": 1},
        ],
        packaging_cny=2,
        shared_purchase_reason="used together in the same task",
    )
    assert bundle["cost_gate"]["status"] == "fail"
    assert bundle["cost_gate"]["total_cny"] == 21


def test_economics_matches_documented_formula_and_is_reproducible():
    econ = example_economics()
    assert econ["calculation_status"] == "calculated"
    assert econ["price_gate"]["status"] == "pass"
    assert econ["purchase_packaging_gate"]["status"] == "pass"
    assert econ["net_revenue_eur"] == pytest.approx(15 / 1.19, abs=1e-6)
    assert econ["cm_before_ads_eur"] == pytest.approx(4.455042, abs=1e-6)
    assert econ["cm_after_ads_eur"] == pytest.approx(1.455042, abs=1e-6)
    assert econ["break_even_cpc_eur"] == pytest.approx(0.445504, abs=1e-6)
    assert econ["trial_procurement_packaging_cny"] == 320


def test_economics_does_not_treat_missing_platform_fee_as_zero():
    econ = pingshen.calculate_economics(
        {
            "price_gross_eur": 15,
            "vat_rate": 0.19,
            "cny_per_eur": 8,
            "purchase_cny": 14,
            "packaging_cny": 2,
        }
    )
    assert econ["calculation_status"] == "pending"
    assert "referral_fee_eur" in econ["missing_inputs"]
    assert "fulfillment_fee_eur" in econ["missing_inputs"]
    assert "cm_before_ads_eur" not in econ


def test_review_recommends_trial_only_after_market_supply_profit_and_sample():
    candidate = {
        "candidate_id": "cand-1",
        "product_name_normalized": "Example Product",
        "source_strategies": ["A", "E", "J"],
        "source_refs": ["fixture"],
    }
    card = jihui.build_opportunity_card(candidate, full_evidence(), ["DE"])
    supply = pingshen.match_supply(
        {"candidate_id": "cand-1", "material": "silicone", "size": "10cm", "pack_count": 1},
        {
            "supplier": "fixture",
            "supplier_sku": "SKU-1",
            "material": "silicone",
            "size": "10cm",
            "pack_count": 1,
            "unit_quote_cny": 14,
            "packaging_cny": 2,
            "sample_status": "passed",
        },
    )
    decision = pingshen.review_development(card, supply, example_economics())
    assert decision["decision_code"] == "TRIAL_RECOMMENDED"
    assert decision["decision_label"] == "建议试销"


def test_review_rejects_hard_cost_failure_with_reason_code():
    card = jihui.build_opportunity_card(
        {"candidate_id": "cand-1", "product_name_normalized": "Example", "source_strategies": ["A"]},
        full_evidence(),
        ["DE"],
    )
    supply = {
        "match_type": "exact",
        "sample_status": "passed",
        "cost_gate": {"status": "fail", "total_cny": 22, "cap_cny": 20},
    }
    decision = pingshen.review_development(card, supply, example_economics())
    assert decision["decision_code"] == "REJECTED"
    assert "PURCHASE_PACKAGING_CAP_FAIL" in decision["reason_codes"]



def test_cross_market_title_similarity_does_not_merge_without_verified_identity():
    rows = [
        {
            "marketplace": "DE",
            "product_name": "Same Looking Product",
            "product_signature": "sig-123",
            "source_strategy": "E",
            "source_ref": "de:1",
        },
        {
            "marketplace": "FR",
            "product_name": "Same Looking Product",
            "product_signature": "sig-123",
            "source_strategy": "E",
            "source_ref": "fr:1",
        },
    ]
    assert len(jihui.merge_candidates(rows)) == 2

    for row in rows:
        row["cross_market_identity_verified"] = True
    merged = jihui.merge_candidates(rows)
    assert len(merged) == 1
    assert merged[0]["dedupe_confidence"] == "medium"


def test_cn_seller_gate_zero_fact_is_a_real_admission_failure():
    candidate = {
        "candidate_id": "cand-cn-zero",
        "product_name_normalized": "Example",
        "source_strategies": ["A"],
    }
    evidence = full_evidence("cand-cn-zero")
    evidence[0]["value"] = 0
    evidence[0]["evidence_status"] = "fact"
    card = jihui.build_opportunity_card(candidate, evidence, ["DE"])
    assert card["cn_seller_gate"]["status"] == "fail"

    supply = {
        "match_type": "exact",
        "sample_status": "passed",
        "cost_gate": {"status": "pass", "total_cny": 16, "cap_cny": 20},
    }
    decision = pingshen.review_development(card, supply, example_economics())
    assert decision["decision_code"] == "REJECTED"
    assert "CN_SELLER_GATE_FAIL" in decision["reason_codes"]

def test_fixed_workbook_has_all_ten_delivery_sheets(tmp_path):
    target = tmp_path / "development.xlsx"
    result = pingshen.export_workbook(
        target,
        {
            "task": {"task_id": "task-fixture"},
            "candidates": [{"candidate_id": "cand-1"}],
            "evidence": full_evidence(),
            "opportunity_cards": [{"candidate_id": "cand-1", "decision_readiness": "ready_for_supply_match"}],
            "supply_match": [{"candidate_id": "cand-1", "supplier_sku": "SKU-1"}],
            "economics": [example_economics()],
            "decision": [{"decision_code": "TRIAL_RECOMMENDED"}],
            "product_master": [{"candidate_id": "cand-1", "fact_status": "confirmed"}],
            "handoff": [{"department": "采购", "task": "confirm quote validity"}],
            "trial_card": [{"candidate_id": "cand-1", "quantity_status": "pending_human_approval"}],
        },
    )
    assert result["sheet_count"] == 10
    assert target.exists()
    with zipfile.ZipFile(target) as z:
        assert all(f"xl/worksheets/sheet{i}.xml" in z.namelist() for i in range(1, 11))
        root = ET.fromstring(z.read("xl/workbook.xml"))
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    names = [sheet.attrib["name"] for sheet in root.findall("s:sheets/s:sheet", ns)]
    assert names == pingshen.load_rules()["workbook_sheets"]
