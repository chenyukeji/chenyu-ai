"""Product Master, handoff, scenario matrix and trial-review helpers."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path


class DeliveryError(ValueError):
    pass



TRIAL_FIELDS = {
    "period",
    "observed_period",
    "active_in_stock_days",
    "sessions",
    "orders",
    "units",
    "revenue",
    "ad_spend",
    "ad_sales",
    "returns",
    "refunds",
    "inventory",
    "stockout_days",
    "rating",
    "actual_landed_cost",
    "contribution_total",
    "source_ref",
}

TRIAL_NUMERIC_FIELDS = {
    "active_in_stock_days",
    "sessions",
    "orders",
    "units",
    "revenue",
    "ad_spend",
    "ad_sales",
    "returns",
    "refunds",
    "inventory",
    "stockout_days",
    "rating",
    "actual_landed_cost",
    "contribution_total",
}


def _trial_num(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise DeliveryError(f"{field} cannot be boolean")
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError as exc:
        raise DeliveryError(f"{field} must be numeric: {value!r}") from exc


def import_trial_observations(path_value, field_map=None):
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        raise DeliveryError(f"trial data file not found: {path}")
    if path.stat().st_size > 20 * 1024 * 1024:
        raise DeliveryError("trial data file exceeds size limit")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("rows") or data.get("observations") or data.get("records")
            if rows is None:
                rows = [data]
        else:
            raise DeliveryError("trial JSON root must be object or array")
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise DeliveryError("trial CSV must have headers")
            rows = list(reader)
    else:
        raise DeliveryError("only .json and .csv trial imports are supported")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise DeliveryError("trial rows must be objects")
    if len(rows) > 50000:
        raise DeliveryError("too many trial rows")

    field_map = field_map or {}
    if not isinstance(field_map, dict):
        raise DeliveryError("field_map must be an object")
    normalized = []
    for index, raw in enumerate(rows, start=1):
        row = {}
        for field in TRIAL_FIELDS:
            source = field_map.get(field, field)
            if source in raw and raw[source] not in ("", None):
                value = raw[source]
                if field in TRIAL_NUMERIC_FIELDS:
                    value = _trial_num(value, field)
                else:
                    value = str(value).strip()
                row[field] = value
        if not (row.get("period") or row.get("observed_period")):
            row["period"] = f"row-{index}"
            row["period_status"] = "synthetic_row_label_only"
        row["source_ref"] = row.get("source_ref") or f"{path.name}#row={index}"
        normalized.append(row)
    return {
        "source": str(path.resolve()),
        "observations": normalized,
        "count": len(normalized),
    }

INITIAL_SCENARIO_PROFILE = {
    "profile_id": "initial-proposed-calibration-v1",
    "status": "proposed_not_calibrated",
    "base": {},
    "conservative": {
        "price_gross_eur_factor": 0.90,
        "cpc_eur_factor": 1.25,
        "ad_cvr_factor": 0.75,
        "purchase_cny_factor": 1.10,
        "inbound_eur_factor": 1.10,
        "returns_reserve_eur_factor": 2.00,
    },
    "optimistic": {
        "price_gross_eur_factor": 1.00,
        "cpc_eur_factor": 0.90,
        "ad_cvr_factor": 1.10,
        "purchase_cny_factor": 0.95,
        "inbound_eur_factor": 0.95,
        "returns_reserve_eur_factor": 0.75,
    },
}


def _apply_adjustments(inputs, adjustments):
    out = copy.deepcopy(inputs)
    for key, factor in adjustments.items():
        if not key.endswith("_factor"):
            continue
        field = key[:-7]
        if out.get(field) is not None:
            out[field] = out[field] * factor
    return out


def calculate_scenario_matrix(calculator, base_inputs, prices=None, profile=None):
    if not isinstance(base_inputs, dict):
        raise DeliveryError("base_inputs must be an object")
    profile = copy.deepcopy(profile or INITIAL_SCENARIO_PROFILE)
    base_price = base_inputs.get("price_gross_eur")
    if prices is None:
        if base_price is None:
            raise DeliveryError("price_gross_eur or explicit prices are required")
        prices = [5.0, float(base_price), 20.0]
    prices = list(dict.fromkeys(float(p) for p in prices))
    if any(p <= 0 for p in prices):
        raise DeliveryError("scenario prices must be positive")

    rows = []
    for price in prices:
        for scenario_name in ("conservative", "base", "optimistic"):
            adjustments = profile.get(scenario_name)
            if not isinstance(adjustments, dict):
                raise DeliveryError(f"scenario profile missing {scenario_name}")
            scenario_inputs = dict(base_inputs)
            scenario_inputs["price_gross_eur"] = price
            scenario_inputs = _apply_adjustments(scenario_inputs, adjustments)
            econ = calculator(scenario_inputs)
            rows.append(
                {
                    "price_reference_eur": price,
                    "scenario": scenario_name,
                    "profile_id": profile.get("profile_id"),
                    "profile_status": profile.get("status"),
                    "adjustments": adjustments,
                    "economics": econ,
                }
            )
    return {"profile": profile, "prices": prices, "rows": rows}


def build_delivery_sections(task, candidate, opportunity_card, supply_match, economics, decision, trial_card=None, confirmed_facts=None):
    confirmed_facts = list(confirmed_facts or [])
    product_facts = {}
    pending_facts = []
    for fact in confirmed_facts:
        if not isinstance(fact, dict) or not fact.get("field"):
            raise DeliveryError("confirmed_facts must contain objects with field")
        status = fact.get("status") or "unconfirmed"
        if status == "confirmed":
            product_facts[fact["field"]] = fact.get("value")
        else:
            pending_facts.append(fact)

    product_master = {
        "candidate_id": candidate.get("candidate_id"),
        "product_name": candidate.get("product_name_normalized"),
        "facts": product_facts,
        "pending_facts": pending_facts,
        "supplier_sku": supply_match.get("supplier_sku"),
        "sample_status": supply_match.get("sample_status"),
        "fact_policy": "confirmed_only_in_facts",
    }

    purchase_tasks = [
        {
            "department": "采购",
            "task": "核对供应商 SKU、报价有效期、MOQ、交期和样品状态",
            "supplier_sku": supply_match.get("supplier_sku"),
            "blocking": decision.get("decision_code") == "QUOTE_SAMPLE",
        }
    ]
    operations_tasks = [
        {
            "department": "运营",
            "task": "按目标站和评审结果准备试销参数，不把开发假设当实际经营数据",
            "marketplace": economics.get("marketplace"),
            "target_price_eur": economics.get("inputs", {}).get("price_gross_eur"),
            "decision_code": decision.get("decision_code"),
        }
    ]
    design_tasks = [
        {
            "department": "美工",
            "task": "仅使用 Product Master 已确认产品事实准备素材与作图需求",
            "confirmed_fact_fields": sorted(product_facts),
            "pending_fact_fields": sorted(str(f.get("field")) for f in pending_facts),
        }
    ]
    handoff = purchase_tasks + operations_tasks + design_tasks

    return {
        "product_master": product_master,
        "handoff": handoff,
        "trial_card": trial_card,
        "source_summary": {
            "candidate_id": candidate.get("candidate_id"),
            "opportunity_readiness": opportunity_card.get("decision_readiness"),
            "decision_code": decision.get("decision_code"),
            "rules_snapshot": task.get("rules_snapshot"),
        },
    }



def build_sample_checklist(candidate_requirements, supply_match, output_mode="single", bundle=None, extra_checks=None):
    if not isinstance(candidate_requirements, dict) or not isinstance(supply_match, dict):
        raise DeliveryError("candidate_requirements and supply_match must be objects")
    checks = []

    def add(check_id, label, expected, source):
        checks.append(
            {
                "check_id": check_id,
                "label": label,
                "expected": expected,
                "source": source,
                "status": "pending_physical_verification",
            }
        )

    add("identity", "供应商 SKU 与目标款式身份", supply_match.get("supplier_sku"), "supply_match")
    for field, label in (
        ("material", "材质"),
        ("size", "尺寸/测量部位"),
        ("pack_count", "销售单位件数"),
        ("color", "颜色/表面"),
    ):
        if candidate_requirements.get(field) is not None:
            add(field, label, candidate_requirements.get(field), "candidate_requirements")
    add("packaging", "完整销售包装、标签与运输保护", "符合当前销售单位定义且无重复计费", "business_rule")
    add("quality", "外观、破损、毛刺、异味、装配/使用质量", "无影响销售和使用的问题", "physical_sample")
    add("dimensions_weight", "包装后尺寸与重量", "实测并记录，用于履约费用复核", "physical_sample")

    if output_mode == "complementary_bundle":
        bundle = bundle or {}
        add("bundle_reason", "组合共同购买理由", bundle.get("shared_purchase_reason"), "bundle_concept")
        add("bundle_compatibility", "组件兼容、数量与实际共同使用", "全部组件可按预期共同使用", "physical_sample")
        add("bundle_packaging", "整套组套方式", "组件不互相损坏、包装尺寸重量可复核", "physical_sample")

    for idx, item in enumerate(extra_checks or [], start=1):
        if isinstance(item, str):
            add(f"extra_{idx}", item, "人工确认", "user")
        elif isinstance(item, dict):
            add(
                item.get("check_id") or f"extra_{idx}",
                item.get("label") or "额外检查",
                item.get("expected"),
                item.get("source") or "user",
            )
        else:
            raise DeliveryError("extra_checks must contain strings or objects")

    return {
        "candidate_id": candidate_requirements.get("candidate_id"),
        "supplier_sku": supply_match.get("supplier_sku"),
        "output_mode": output_mode,
        "checks": checks,
        "completion_rule": "all applicable checks require physical verification; generated checklist is not a sample result",
    }


def calculate_trial_funding(economics, planned_units, ad_budget_eur=0, fixed_cost_cny=0, other_initial_cash_cny=0):
    if not isinstance(economics, dict):
        raise DeliveryError("economics must be an object")
    inputs = economics.get("inputs") or {}
    quantity = _trial_num(planned_units, "planned_units")
    if quantity is None or quantity <= 0:
        raise DeliveryError("planned_units must be > 0")
    purchase = _trial_num(inputs.get("purchase_cny"), "purchase_cny")
    packaging = _trial_num(inputs.get("packaging_cny"), "packaging_cny")
    fx = _trial_num(inputs.get("cny_per_eur"), "cny_per_eur")
    inbound_eur = _trial_num(inputs.get("inbound_eur"), "inbound_eur")
    if None in {purchase, packaging, fx, inbound_eur}:
        return {
            "status": "pending",
            "planned_units": quantity,
            "missing_inputs": [
                field
                for field, value in (
                    ("purchase_cny", purchase),
                    ("packaging_cny", packaging),
                    ("cny_per_eur", fx),
                    ("inbound_eur", inbound_eur),
                )
                if value is None
            ],
        }
    ad_budget = _trial_num(ad_budget_eur, "ad_budget_eur") or 0.0
    fixed = _trial_num(fixed_cost_cny, "fixed_cost_cny") or 0.0
    other = _trial_num(other_initial_cash_cny, "other_initial_cash_cny") or 0.0
    if min(ad_budget, fixed, other) < 0:
        raise DeliveryError("funding components cannot be negative")

    procurement_packaging = quantity * (purchase + packaging)
    inbound_cny = quantity * inbound_eur * fx
    ad_cny = ad_budget * fx
    total = procurement_packaging + inbound_cny + ad_cny + fixed + other
    return {
        "status": "calculated",
        "planned_units": quantity,
        "components_cny": {
            "procurement_packaging": round(procurement_packaging, 6),
            "inbound": round(inbound_cny, 6),
            "ad_budget": round(ad_cny, 6),
            "fixed_cost": round(fixed, 6),
            "other_initial_cash": round(other, 6),
        },
        "initial_cash_requirement_cny": round(total, 6),
        "excludes": [
            "timing-specific deposits/tail-payments not separately supplied",
            "recoverable import VAT unless explicitly supplied as other_initial_cash",
            "future replenishment deposits",
        ],
        "boundary": "funding requirement only; not a purchase quantity approval",
    }

def review_trial(trial_plan, observations):
    if not isinstance(trial_plan, dict):
        raise DeliveryError("trial_plan must be an object")
    if not isinstance(observations, list) or not observations:
        raise DeliveryError("observations must be a non-empty list")

    totals = {
        "sessions": 0.0,
        "orders": 0.0,
        "revenue": 0.0,
        "ad_spend": 0.0,
        "ad_sales": 0.0,
        "returns": 0.0,
        "refunds": 0.0,
        "stockout_days": 0.0,
    }
    latest_inventory = None
    contribution_total = 0.0
    contribution_known = True

    for row in observations:
        if not isinstance(row, dict):
            raise DeliveryError("observation rows must be objects")
        for field in totals:
            value = row.get(field)
            if value is not None:
                totals[field] += float(value)
        if row.get("inventory") is not None:
            latest_inventory = float(row["inventory"])
        if row.get("contribution_total") is None:
            contribution_known = False
        else:
            contribution_total += float(row["contribution_total"])

    metrics = {
        **totals,
        "inventory": latest_inventory,
        "conversion_rate": totals["orders"] / totals["sessions"] if totals["sessions"] > 0 else None,
        "acos": totals["ad_spend"] / totals["ad_sales"] if totals["ad_sales"] > 0 else None,
        "tacos": totals["ad_spend"] / totals["revenue"] if totals["revenue"] > 0 else None,
        "return_rate": totals["returns"] / totals["orders"] if totals["orders"] > 0 else None,
        "contribution_total": contribution_total if contribution_known else None,
    }

    thresholds = trial_plan.get("review_thresholds") or {}
    failures = []
    warnings = []

    def max_check(metric, threshold_key, reason):
        threshold = thresholds.get(threshold_key)
        value = metrics.get(metric)
        if threshold is not None and value is not None and value > float(threshold):
            failures.append(reason)

    def min_check(metric, threshold_key, reason):
        threshold = thresholds.get(threshold_key)
        value = metrics.get(metric)
        if threshold is not None and value is not None and value < float(threshold):
            failures.append(reason)

    max_check("acos", "max_acos", "ACOS_ABOVE_LIMIT")
    max_check("return_rate", "max_return_rate", "RETURN_RATE_ABOVE_LIMIT")
    max_check("stockout_days", "max_stockout_days", "STOCKOUT_DAYS_ABOVE_LIMIT")
    min_check("orders", "min_orders", "ORDERS_BELOW_MINIMUM")
    min_check("contribution_total", "min_contribution_total", "CONTRIBUTION_BELOW_MINIMUM")

    if not thresholds:
        warnings.append("review_thresholds_missing")
    if metrics["contribution_total"] is None:
        warnings.append("contribution_total_missing")

    exit_reasons = {"RETURN_RATE_ABOVE_LIMIT", "CONTRIBUTION_BELOW_MINIMUM"}
    if any(reason in exit_reasons for reason in failures):
        action = "exit_review"
    elif latest_inventory is not None and latest_inventory <= 0 and not failures and totals["orders"] > 0:
        action = "replenishment_review"
    elif failures:
        action = "adjust"
    else:
        action = "continue_test"

    return {
        "trial_id": trial_plan.get("trial_id"),
        "metrics": metrics,
        "thresholds": thresholds,
        "failure_reasons": failures,
        "warnings": warnings,
        "recommended_action": action,
        "action_boundary": "recommendation_only_no_ads_no_purchase_no_inventory_action",
    }
