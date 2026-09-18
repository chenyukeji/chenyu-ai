"""Supply, economics, review and XLSX delivery helpers for chenyu-kaifa-pingshen."""
from __future__ import annotations

import json
import math
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sourcing_import import QuoteImportError, import_supplier_quotes
from delivery_trial import DeliveryError, build_delivery_sections, build_sample_checklist, calculate_scenario_matrix, calculate_trial_funding, import_trial_observations, review_trial

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"


class ContractError(ValueError):
    pass


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _num(value, field: str, required: bool = False):
    if value is None:
        if required:
            raise ContractError(f"{field} is required")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be numeric")
    if not math.isfinite(float(value)):
        raise ContractError(f"{field} must be finite")
    return float(value)


def _norm(value):
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    return value


def cost_gate(purchase_cny, packaging_cny, cap=None) -> dict:
    rules = load_rules()
    cap = float(rules["purchase_packaging_cap_cny"] if cap is None else cap)
    purchase = _num(purchase_cny, "purchase_cny")
    packaging = _num(packaging_cny, "packaging_cny")
    if purchase is None or packaging is None:
        return {"status": "unknown", "cap_cny": cap, "total_cny": None}
    total = purchase + packaging
    return {
        "status": "pass" if total <= cap else "fail",
        "cap_cny": cap,
        "total_cny": round(total, 6),
    }


def match_supply(candidate_requirements: dict, supplier_item: dict, cap_cny=None) -> dict:
    if not isinstance(candidate_requirements, dict) or not isinstance(supplier_item, dict):
        raise ContractError("candidate_requirements and supplier_item must be objects")
    required_fields = candidate_requirements.get("required_fields")
    if required_fields is None:
        required_fields = [
            field
            for field in ("material", "size", "pack_count")
            if candidate_requirements.get(field) is not None
        ]
    if not isinstance(required_fields, list):
        raise ContractError("required_fields must be a list")

    mismatches = []
    missing = []
    for field in required_fields:
        expected = candidate_requirements.get(field)
        actual = supplier_item.get(field)
        if expected is None or actual is None:
            missing.append(field)
        elif _norm(expected) != _norm(actual):
            mismatches.append({"field": field, "expected": expected, "actual": actual})

    if missing:
        match_type = "unknown"
    elif mismatches:
        match_type = "alternative"
    else:
        optional_fields = ("color", "finish", "shape")
        optional_diff = any(
            candidate_requirements.get(f) is not None
            and supplier_item.get(f) is not None
            and _norm(candidate_requirements.get(f)) != _norm(supplier_item.get(f))
            for f in optional_fields
        )
        match_type = "compatible" if optional_diff else "exact"

    gate = cost_gate(supplier_item.get("unit_quote_cny"), supplier_item.get("packaging_cny"), cap_cny)
    return {
        "candidate_id": candidate_requirements.get("candidate_id"),
        "supplier": supplier_item.get("supplier"),
        "supplier_sku": supplier_item.get("supplier_sku"),
        "match_type": match_type,
        "required_fields": required_fields,
        "missing_fields": missing,
        "mismatch_notes": mismatches,
        "unit_quote_cny": supplier_item.get("unit_quote_cny"),
        "packaging_cny": supplier_item.get("packaging_cny"),
        "moq": supplier_item.get("moq"),
        "lead_time_days": supplier_item.get("lead_time_days"),
        "sample_available": supplier_item.get("sample_available"),
        "sample_status": supplier_item.get("sample_status") or "not_checked",
        "quote_observed_at": supplier_item.get("quote_observed_at"),
        "quote_valid_until": supplier_item.get("quote_valid_until"),
        "cost_gate": gate,
    }



def build_multipack(supplier_sku, unit_quote_cny, pack_count, packaging_cny, cap_cny=None) -> dict:
    count = _num(pack_count, "pack_count", required=True)
    if count < 2 or int(count) != count:
        raise ContractError("pack_count must be an integer >= 2")
    unit_quote = _num(unit_quote_cny, "unit_quote_cny")
    packaging = _num(packaging_cny, "packaging_cny")
    purchase_total = None if unit_quote is None else unit_quote * count
    gate = cost_gate(purchase_total, packaging, cap_cny)
    return {
        "output_mode": "multipack",
        "supplier_sku": supplier_sku,
        "pack_count": int(count),
        "unit_quote_cny": unit_quote,
        "purchase_total_cny": None if purchase_total is None else round(purchase_total, 6),
        "packaging_cny": packaging,
        "cost_gate": gate,
    }

def build_bundle(components: list[dict], packaging_cny, shared_purchase_reason: str, cap_cny=None) -> dict:
    if not isinstance(components, list) or len(components) < 2:
        raise ContractError("a complementary bundle needs at least two components")
    if not shared_purchase_reason or not str(shared_purchase_reason).strip():
        raise ContractError("shared_purchase_reason is required")
    purchase_total = 0.0
    missing = []
    normalized_components = []
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise ContractError("each component must be an object")
        quote = _num(component.get("unit_quote_cny"), f"components[{index}].unit_quote_cny")
        qty = _num(component.get("quantity", 1), f"components[{index}].quantity", required=True)
        if quote is None:
            missing.append(index)
        else:
            purchase_total += quote * qty
        normalized_components.append(
            {
                "supplier_sku": component.get("supplier_sku"),
                "quantity": qty,
                "unit_quote_cny": quote,
            }
        )
    packaging = _num(packaging_cny, "packaging_cny")
    gate = (
        {"status": "unknown", "cap_cny": float(cap_cny or load_rules()["purchase_packaging_cap_cny"]), "total_cny": None}
        if missing or packaging is None
        else cost_gate(purchase_total, packaging, cap_cny)
    )
    return {
        "output_mode": "complementary_bundle",
        "components": normalized_components,
        "shared_purchase_reason": str(shared_purchase_reason).strip(),
        "purchase_total_cny": None if missing else round(purchase_total, 6),
        "packaging_cny": packaging,
        "cost_gate": gate,
        "pending_component_quotes": missing,
    }


CORE_ECON_FIELDS = (
    "price_gross_eur",
    "vat_rate",
    "cny_per_eur",
    "purchase_cny",
    "packaging_cny",
    "referral_fee_eur",
    "fulfillment_fee_eur",
    "inbound_eur",
)


def calculate_economics(inputs: dict) -> dict:
    if not isinstance(inputs, dict):
        raise ContractError("economics inputs must be an object")
    rules = load_rules()
    marketplace = inputs.get("marketplace")
    if marketplace is not None and str(marketplace).upper() not in set(rules["sales_marketplaces"]):
        raise ContractError(f"unsupported economics marketplace: {marketplace}")
    values = {field: _num(inputs.get(field), field) for field in CORE_ECON_FIELDS}
    missing = [field for field, value in values.items() if value is None]

    price = values["price_gross_eur"]
    purchase = values["purchase_cny"]
    packaging = values["packaging_cny"]
    configured_price = rules["target_price_eur"]
    price_gate = {
        "status": "unknown" if price is None else (
            "pass" if configured_price["min"] <= price <= configured_price["max"] else "fail"
        ),
        "range_eur": [configured_price["min"], configured_price["max"]],
        "value_eur": price,
    }
    purchase_gate = cost_gate(purchase, packaging)

    result = {
        "marketplace": inputs.get("marketplace"),
        "fulfillment_path": inputs.get("fulfillment_path"),
        "calculation_status": "pending" if missing else "calculated",
        "missing_inputs": list(missing),
        "price_gate": price_gate,
        "purchase_packaging_gate": purchase_gate,
        "inputs": dict(inputs),
    }
    if missing:
        return result

    vat = values["vat_rate"]
    fx = values["cny_per_eur"]
    if vat < 0 or vat >= 1:
        raise ContractError("vat_rate must be >= 0 and < 1")
    if fx <= 0:
        raise ContractError("cny_per_eur must be > 0")

    net_revenue = price / (1 + vat)
    procurement_packaging_eur = (purchase + packaging) / fx
    storage = _num(inputs.get("storage_eur", 0), "storage_eur", required=True)
    returns_reserve = _num(inputs.get("returns_reserve_eur", 0), "returns_reserve_eur", required=True)
    other_variable = _num(inputs.get("other_variable_eur", 0), "other_variable_eur", required=True)

    cm_before_ads = (
        net_revenue
        - values["referral_fee_eur"]
        - values["fulfillment_fee_eur"]
        - procurement_packaging_eur
        - values["inbound_eur"]
        - storage
        - returns_reserve
        - other_variable
    )

    ad_share = _num(inputs.get("ad_order_share"), "ad_order_share")
    cpc = _num(inputs.get("cpc_eur"), "cpc_eur")
    cvr = _num(inputs.get("ad_cvr"), "ad_cvr")
    ad_cost_per_total_order = None
    cm_after_ads = None
    ad_pending = []

    if ad_share == 0:
        ad_cost_per_total_order = 0.0
        cm_after_ads = cm_before_ads
    elif ad_share is not None and cpc is not None and cvr is not None:
        if not 0 <= ad_share <= 1:
            raise ContractError("ad_order_share must be between 0 and 1")
        if cvr <= 0 or cvr > 1:
            raise ContractError("ad_cvr must be > 0 and <= 1")
        ad_cost_per_total_order = ad_share * cpc / cvr
        cm_after_ads = cm_before_ads - ad_cost_per_total_order
    else:
        for field, value in (("ad_order_share", ad_share), ("cpc_eur", cpc), ("ad_cvr", cvr)):
            if value is None:
                ad_pending.append(field)

    ad_sales_per_order = _num(inputs.get("ad_sales_per_order_eur"), "ad_sales_per_order_eur")
    break_even_acos = None
    if ad_sales_per_order is not None:
        if ad_sales_per_order <= 0:
            raise ContractError("ad_sales_per_order_eur must be > 0")
        break_even_acos = cm_before_ads / ad_sales_per_order

    break_even_cpc = None
    if cvr is not None:
        if cvr <= 0 or cvr > 1:
            raise ContractError("ad_cvr must be > 0 and <= 1")
        break_even_cpc = cm_before_ads * cvr

    result.update(
        {
            "net_revenue_eur": round(net_revenue, 6),
            "procurement_packaging_eur": round(procurement_packaging_eur, 6),
            "cm_before_ads_eur": round(cm_before_ads, 6),
            "ad_cost_per_total_order_eur": None if ad_cost_per_total_order is None else round(ad_cost_per_total_order, 6),
            "cm_after_ads_eur": None if cm_after_ads is None else round(cm_after_ads, 6),
            "contribution_rate_after_ads": None if cm_after_ads is None else round(cm_after_ads / net_revenue, 8),
            "break_even_acos": None if break_even_acos is None else round(break_even_acos, 8),
            "break_even_acos_basis": "explicit ad_sales_per_order_eur" if break_even_acos is not None else "pending ad_sales_per_order_eur",
            "break_even_cpc_eur": None if break_even_cpc is None else round(break_even_cpc, 6),
            "advertising_pending_inputs": ad_pending,
        }
    )

    trial_units = _num(inputs.get("trial_units"), "trial_units")
    if trial_units is not None:
        if trial_units < 0:
            raise ContractError("trial_units must be >= 0")
        result["trial_procurement_packaging_cny"] = round(trial_units * (purchase + packaging), 6)
        result["trial_units"] = trial_units
    return result


def review_development(opportunity_card: dict, supply_match: dict, economics: dict) -> dict:
    rules = load_rules()
    reasons = []
    blocking = []

    cn_gate = (opportunity_card or {}).get("cn_seller_gate", {}).get("status")
    cost_status = (supply_match or {}).get("cost_gate", {}).get("status")
    price_status = (economics or {}).get("price_gate", {}).get("status")
    econ_cost_status = (economics or {}).get("purchase_packaging_gate", {}).get("status")

    hard_fail = []
    if cn_gate == "fail":
        hard_fail.append("CN_SELLER_GATE_FAIL")
    if cost_status == "fail" or econ_cost_status == "fail":
        hard_fail.append("PURCHASE_PACKAGING_CAP_FAIL")
    if price_status == "fail":
        hard_fail.append("TARGET_PRICE_RANGE_FAIL")
    if hard_fail:
        return {
            "decision_code": "REJECTED",
            "decision_label": rules["decision_labels"]["REJECTED"],
            "reason_codes": hard_fail,
            "blocking_items": [],
            "next_actions": ["archive_reasoned_rejection"],
        }

    if opportunity_card.get("decision_readiness") != "ready_for_supply_match" or cn_gate == "unknown":
        blocking.extend(opportunity_card.get("pending_verification") or [])
        if cn_gate == "unknown":
            blocking.append("cn_seller_evidence")
        reasons.append("MARKET_EVIDENCE_INCOMPLETE")
        return {
            "decision_code": "NEEDS_MORE_RESEARCH",
            "decision_label": rules["decision_labels"]["NEEDS_MORE_RESEARCH"],
            "reason_codes": reasons,
            "blocking_items": sorted(set(blocking)),
            "next_actions": list(opportunity_card.get("next_actions") or [])[:3],
        }

    match_type = supply_match.get("match_type")
    if match_type in {"unknown", "alternative"} or cost_status == "unknown":
        reasons.append("SUPPLY_MATCH_OR_QUOTE_INCOMPLETE")
        blocking.extend(supply_match.get("missing_fields") or [])
        return {
            "decision_code": "QUOTE_SAMPLE",
            "decision_label": rules["decision_labels"]["QUOTE_SAMPLE"],
            "reason_codes": reasons,
            "blocking_items": sorted(set(blocking)),
            "next_actions": ["confirm_supplier_sku", "confirm_quote", "verify_sample"],
        }

    if economics.get("calculation_status") != "calculated":
        return {
            "decision_code": "NEEDS_MORE_RESEARCH",
            "decision_label": rules["decision_labels"]["NEEDS_MORE_RESEARCH"],
            "reason_codes": ["ECONOMICS_INPUTS_INCOMPLETE"],
            "blocking_items": list(economics.get("missing_inputs") or []),
            "next_actions": ["complete_fee_and_cost_inputs"],
        }

    cm_after = economics.get("cm_after_ads_eur")
    if cm_after is None:
        return {
            "decision_code": "NEEDS_MORE_RESEARCH",
            "decision_label": rules["decision_labels"]["NEEDS_MORE_RESEARCH"],
            "reason_codes": ["AD_SCENARIO_INCOMPLETE"],
            "blocking_items": list(economics.get("advertising_pending_inputs") or []),
            "next_actions": ["set_explicit_cpc_cvr_and_ad_order_share"],
        }
    if cm_after <= 0:
        return {
            "decision_code": "HOLD",
            "decision_label": rules["decision_labels"]["HOLD"],
            "reason_codes": ["BASE_SCENARIO_NONPOSITIVE_CONTRIBUTION"],
            "blocking_items": [],
            "next_actions": ["reprice_or_reduce_cost", "rerun_economics"],
        }

    if supply_match.get("sample_status") not in {"passed", "verified"}:
        return {
            "decision_code": "QUOTE_SAMPLE",
            "decision_label": rules["decision_labels"]["QUOTE_SAMPLE"],
            "reason_codes": ["SAMPLE_NOT_VERIFIED"],
            "blocking_items": ["sample_status"],
            "next_actions": ["verify_sample"],
        }

    return {
        "decision_code": "TRIAL_RECOMMENDED",
        "decision_label": rules["decision_labels"]["TRIAL_RECOMMENDED"],
        "reason_codes": ["MARKET_SUPPLY_ECONOMICS_SAMPLE_READY"],
        "blocking_items": [],
        "next_actions": ["create_trial_card", "human_approve_trial_quantity"],
    }


def create_trial_card(task: dict, candidate: dict, economics: dict, decision: dict, plan: dict | None = None) -> dict:
    plan = dict(plan or {})
    return {
        "trial_id": plan.get("trial_id"),
        "candidate_id": candidate.get("candidate_id"),
        "marketplace": plan.get("marketplace") or economics.get("marketplace"),
        "decision_code": decision.get("decision_code"),
        "planned_price_eur": plan.get("planned_price_eur") or economics.get("inputs", {}).get("price_gross_eur"),
        "planned_units": plan.get("planned_units"),
        "ad_budget_eur": plan.get("ad_budget_eur"),
        "loss_budget_cny": plan.get("loss_budget_cny"),
        "observation_days": plan.get("observation_days"),
        "success_conditions": list(plan.get("success_conditions") or []),
        "exit_conditions": list(plan.get("exit_conditions") or []),
        "budget_cny": task.get("budget_cny"),
        "quantity_status": "pending_human_approval" if plan.get("planned_units") is None else "proposed_not_ordered",
        "execution_boundary": "plan_only_no_purchase_no_ads",
    }


def _excel_col(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _xml_safe_text(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = str(value)
    # JSON/tool transports can occasionally deliver UTF-16 surrogate pairs as
    # separate code units. Normalize valid pairs and replace unpaired surrogates.
    text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
    # XML 1.0 permits tabs/newlines/CR plus the normal Unicode scalar ranges.
    text = "".join(
        ch if (
            ch in "\t\n\r"
            or 0x20 <= ord(ch) <= 0xD7FF
            or 0xE000 <= ord(ch) <= 0xFFFD
            or 0x10000 <= ord(ch) <= 0x10FFFF
        ) else "\uFFFD"
        for ch in text
    )
    return escape(text)


def _cell_xml(ref: str, value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = _xml_safe_text(value)
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _rows_for(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [row if isinstance(row, dict) else {"value": row} for row in value]
    return [{"value": value}]


def _worksheet_xml(rows: list[dict]) -> str:
    headers = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    xml_rows = []
    if headers:
        cells = "".join(_cell_xml(f"{_excel_col(i+1)}1", h) for i, h in enumerate(headers))
        xml_rows.append(f'<row r="1">{cells}</row>')
        for r_index, row in enumerate(rows, start=2):
            cells = "".join(
                _cell_xml(f"{_excel_col(c_index+1)}{r_index}", row.get(header))
                for c_index, header in enumerate(headers)
            )
            xml_rows.append(f'<row r="{r_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )


SECTION_KEYS = {
    "00_Task": "task",
    "01_Candidates": "candidates",
    "02_Evidence": "evidence",
    "03_Opportunity_Cards": "opportunity_cards",
    "04_Supply_Match": "supply_match",
    "05_Economics": "economics",
    "06_Decision": "decision",
    "07_Product_Master": "product_master",
    "08_Handoff": "handoff",
    "09_Trial_Card": "trial_card",
}


def export_workbook(output_path: str | Path, sections: dict) -> dict:
    rules = load_rules()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet_names = list(rules["workbook_sheets"])
    if sheet_names != list(SECTION_KEYS):
        raise ContractError("runtime workbook_sheets do not match exporter contract")

    temp_output = output.with_name(output.name + ".tmp")
    if temp_output.exists():
        temp_output.unlink()

    workbook_sheets = []
    rels = []
    overrides = []
    try:
        with zipfile.ZipFile(temp_output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for idx, sheet_name in enumerate(sheet_names, start=1):
                workbook_sheets.append(
                    f'<sheet name="{escape(sheet_name)}" sheetId="{idx}" r:id="rId{idx}"/>'
                )
                rels.append(
                    f'<Relationship Id="rId{idx}" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    f'Target="worksheets/sheet{idx}.xml"/>'
                )
                overrides.append(
                    f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                )
                rows = _rows_for(sections.get(SECTION_KEYS[sheet_name]))
                z.writestr(f"xl/worksheets/sheet{idx}.xml", _worksheet_xml(rows))

            z.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                + "".join(overrides)
                + "</Types>",
            )
            z.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>',
            )
            z.writestr(
                "xl/workbook.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>',
            )
            z.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(rels)
                + "</Relationships>",
            )
        temp_output.replace(output)
    except Exception:
        if temp_output.exists():
            temp_output.unlink()
        raise

    return {"path": str(output.resolve()), "sheets": sheet_names, "sheet_count": len(sheet_names)}


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ContractError("input must be a JSON object")
    action = payload.get("skill_action")
    if action == "status":
        rules = load_rules()
        return {
            "ok": True,
            "skill": "chenyu-kaifa-pingshen",
            "config_revision": rules["config_revision"],
            "actions": [
                "status",
                "import_supplier_quotes",
                "match_supply",
                "build_multipack",
                "build_bundle",
                "calculate_economics",
                "calculate_scenario_matrix",
                "review",
                "create_trial_card",
                "build_delivery_sections",
                "build_sample_checklist",
                "calculate_trial_funding",
                "import_trial_data",
                "review_trial",
                "export_workbook",
            ],
        }
    if action == "import_supplier_quotes":
        path = payload.get("path")
        if not path:
            raise ContractError("path is required")
        return {
            "ok": True,
            "quotes": import_supplier_quotes(
                path,
                payload.get("field_map"),
                payload.get("planned_quantity"),
                payload.get("as_of_date"),
            ),
        }
    if action == "match_supply":
        return {
            "ok": True,
            "supply_match": match_supply(
                payload.get("candidate_requirements") or {},
                payload.get("supplier_item") or {},
                payload.get("cap_cny"),
            ),
        }
    if action == "build_multipack":
        return {
            "ok": True,
            "multipack": build_multipack(
                payload.get("supplier_sku"),
                payload.get("unit_quote_cny"),
                payload.get("pack_count"),
                payload.get("packaging_cny"),
                payload.get("cap_cny"),
            ),
        }
    if action == "build_bundle":
        return {
            "ok": True,
            "bundle": build_bundle(
                payload.get("components") or [],
                payload.get("packaging_cny"),
                payload.get("shared_purchase_reason"),
                payload.get("cap_cny"),
            ),
        }
    if action == "calculate_economics":
        return {"ok": True, "economics": calculate_economics(payload.get("inputs") or {})}
    if action == "calculate_scenario_matrix":
        return {
            "ok": True,
            "scenario_matrix": calculate_scenario_matrix(
                calculate_economics,
                payload.get("base_inputs") or {},
                payload.get("prices"),
                payload.get("profile"),
            ),
        }
    if action == "review":
        return {
            "ok": True,
            "decision": review_development(
                payload.get("opportunity_card") or {},
                payload.get("supply_match") or {},
                payload.get("economics") or {},
            ),
        }
    if action == "create_trial_card":
        return {
            "ok": True,
            "trial_card": create_trial_card(
                payload.get("task") or {},
                payload.get("candidate") or {},
                payload.get("economics") or {},
                payload.get("decision") or {},
                payload.get("plan"),
            ),
        }
    if action == "build_sample_checklist":
        return {
            "ok": True,
            "sample_checklist": build_sample_checklist(
                payload.get("candidate_requirements") or {},
                payload.get("supply_match") or {},
                payload.get("output_mode") or "single",
                payload.get("bundle"),
                payload.get("extra_checks"),
            ),
        }
    if action == "calculate_trial_funding":
        return {
            "ok": True,
            "trial_funding": calculate_trial_funding(
                payload.get("economics") or {},
                payload.get("planned_units"),
                payload.get("ad_budget_eur", 0),
                payload.get("fixed_cost_cny", 0),
                payload.get("other_initial_cash_cny", 0),
            ),
        }
    if action == "build_delivery_sections":
        return {
            "ok": True,
            "delivery": build_delivery_sections(
                payload.get("task") or {},
                payload.get("candidate") or {},
                payload.get("opportunity_card") or {},
                payload.get("supply_match") or {},
                payload.get("economics") or {},
                payload.get("decision") or {},
                payload.get("trial_card"),
                payload.get("confirmed_facts"),
            ),
        }
    if action == "import_trial_data":
        path = payload.get("path")
        if not path:
            raise ContractError("path is required")
        return {
            "ok": True,
            "trial_data": import_trial_observations(path, payload.get("field_map")),
        }
    if action == "review_trial":
        observations = payload.get("observations")
        if observations is None and payload.get("trial_data"):
            observations = payload["trial_data"].get("observations")
        return {
            "ok": True,
            "trial_review": review_trial(
                payload.get("trial_plan") or {},
                observations or [],
            ),
        }
    if action == "export_workbook":
        path = payload.get("output_path")
        if not path:
            raise ContractError("output_path is required")
        return {"ok": True, "workbook": export_workbook(path, payload.get("sections") or {})}
    raise ContractError(f"unknown skill_action: {action}")


def main() -> None:
    try:
        result = handle(json.loads(sys.stdin.buffer.read().decode("utf-8-sig")))
    except (json.JSONDecodeError, ContractError, QuoteImportError, DeliveryError, OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        result = {"ok": False, "code": "invalid_input", "message": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
