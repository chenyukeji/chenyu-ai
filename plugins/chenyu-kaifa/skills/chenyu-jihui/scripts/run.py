"""Candidate-pool and opportunity-card helpers for chenyu-jihui (stdlib only)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"


class ContractError(ValueError):
    pass


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def _strategy_list(row: dict) -> list[str]:
    values = row.get("source_strategies")
    if values is None:
        one = row.get("source_strategy")
        values = [] if one is None else [one]
    if not isinstance(values, list):
        raise ContractError("source_strategies must be a list")
    return [str(v) for v in values if v]


def _source_refs(row: dict) -> list[str]:
    values = row.get("source_refs")
    if values is None:
        one = row.get("source_ref")
        values = [] if one is None else [one]
    if not isinstance(values, list):
        raise ContractError("source_refs must be a list")
    return [str(v) for v in values if v]


def _identity(row: dict) -> tuple[str, str, str]:
    market = str(row.get("marketplace") or row.get("source_market") or "").upper()
    asin = str(row.get("asin") or "").upper()
    parent = str(row.get("parent_asin") or "").upper()
    signature = str(row.get("product_signature") or "").strip().lower()
    if market and parent:
        return ("parent", market, parent)
    if market and asin:
        return ("asin", market, asin)
    if signature and row.get("cross_market_identity_verified") is True:
        return ("signature", "cross_market", signature)
    fallback = str(row.get("source_entity_id") or row.get("source_ref") or "")
    if not fallback:
        fallback = json.dumps(
            {
                "market": market,
                "name": row.get("product_name") or row.get("product_name_normalized"),
                "signature": signature,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    return ("source", market or "unknown", fallback)


def _listing_projection(row: dict) -> dict:
    fields = (
        "marketplace",
        "asin",
        "parent_asin",
        "selected_variant",
        "price",
        "currency",
        "estimated_sales",
        "sales_period",
        "sales_level",
        "fulfillment",
        "seller_location",
        "observed_at",
        "source_available_date",
    )
    return {k: row.get(k) for k in fields if row.get(k) is not None}


def merge_candidates(rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list):
        raise ContractError("candidates must be a list")
    rules = load_rules()
    registry = set(rules["strategy_registry"])
    groups: dict[tuple[str, str, str], dict] = {}

    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("each candidate must be an object")
        strategies = _strategy_list(row)
        invalid = [sid for sid in strategies if sid not in registry]
        if invalid:
            raise ContractError(f"unknown strategy ids: {invalid}")

        key = _identity(row)
        key_text = "|".join(key)
        record = groups.get(key)
        if record is None:
            confidence = {"parent": "high", "asin": "high", "signature": "medium", "source": "low"}[key[0]]
            record = {
                "candidate_id": row.get("candidate_id") or _stable_id("cand", key_text),
                "need_cluster": row.get("need_cluster"),
                "product_name_normalized": row.get("product_name_normalized") or row.get("product_name"),
                "product_signature": row.get("product_signature"),
                "marketplace_listings": [],
                "source_strategies": [],
                "source_refs": [],
                "first_seen_at": row.get("first_seen_at") or row.get("observed_at"),
                "dedupe_confidence": confidence,
                "merge_reason": [f"identity:{key[0]}"],
                "research_status": row.get("research_status") or "DISCOVERED",
                "sales_aggregation": {
                    "status": "not_aggregated",
                    "reason": "parent/child and source metric scopes must be reconciled before summing",
                },
                "source_record_count": 0,
            }
            groups[key] = record
        else:
            if f"identity:{key[0]}" not in record["merge_reason"]:
                record["merge_reason"].append(f"identity:{key[0]}")

        for sid in strategies:
            if sid not in record["source_strategies"]:
                record["source_strategies"].append(sid)
        for ref in _source_refs(row):
            if ref not in record["source_refs"]:
                record["source_refs"].append(ref)

        listing = _listing_projection(row)
        if listing:
            identity = (
                listing.get("marketplace"),
                listing.get("asin"),
                listing.get("parent_asin"),
                listing.get("observed_at"),
            )
            existing = {
                (x.get("marketplace"), x.get("asin"), x.get("parent_asin"), x.get("observed_at"))
                for x in record["marketplace_listings"]
            }
            if identity not in existing:
                record["marketplace_listings"].append(listing)

        first_seen = row.get("first_seen_at") or row.get("observed_at")
        if first_seen and (not record.get("first_seen_at") or str(first_seen) < str(record["first_seen_at"])):
            record["first_seen_at"] = first_seen
        record["source_record_count"] += 1

    return list(groups.values())


REQUIRED_EVIDENCE_FIELDS = [
    "cn_seller_evidence",
    "target_market_demand",
    "comparable_competition",
    "comparable_price",
    "product_specs",
    "review_pain_points",
    "fulfillment_and_delivery",
]


def _cn_gate(items: list[dict]) -> dict:
    usable = [e for e in items if e.get("evidence_status") in {"fact", "estimate"}]
    if not usable:
        return {"status": "unknown", "reason": "no usable CN seller evidence"}
    values = [e.get("value") for e in usable]
    for value in values:
        if value is True:
            return {"status": "pass", "reason": "at least one comparable CN seller evidenced"}
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 1:
            return {"status": "pass", "reason": "at least one comparable CN seller evidenced"}
    facts = [e for e in usable if e.get("evidence_status") == "fact"]
    if facts and all((e.get("value") is False) or (isinstance(e.get("value"), (int, float)) and e.get("value") == 0) for e in facts):
        return {"status": "fail", "reason": "fact evidence found zero comparable CN sellers"}
    return {"status": "unknown", "reason": "CN seller evidence does not prove pass or fail"}


def build_opportunity_card(candidate: dict, evidence: list[dict], target_marketplaces: list[str] | None = None) -> dict:
    if not isinstance(candidate, dict):
        raise ContractError("candidate must be an object")
    if not isinstance(evidence, list):
        raise ContractError("evidence must be a list")
    rules = load_rules()
    allowed_status = set(rules["evidence_statuses"])
    by_field: dict[str, list[dict]] = {}

    for item in evidence:
        if not isinstance(item, dict):
            raise ContractError("each evidence item must be an object")
        status = item.get("evidence_status")
        if status not in allowed_status:
            raise ContractError(f"invalid evidence_status: {status}")
        field = item.get("field")
        if not field:
            raise ContractError("evidence.field is required")
        by_field.setdefault(field, []).append(item)

    missing = []
    evidence_summary = {}
    for field in REQUIRED_EVIDENCE_FIELDS:
        items = by_field.get(field, [])
        usable = [e for e in items if e.get("evidence_status") != "pending_verification"]
        if not usable:
            missing.append(field)
        evidence_summary[field] = items or [
            {
                "field": field,
                "value": None,
                "evidence_status": "pending_verification",
                "notes": "required evidence not supplied",
            }
        ]

    markets = target_marketplaces or list(rules["sales_marketplaces"])
    return {
        "candidate_id": candidate.get("candidate_id"),
        "opportunity_name": candidate.get("product_name_normalized"),
        "need_cluster": candidate.get("need_cluster"),
        "target_marketplaces": markets,
        "source_strategies": list(candidate.get("source_strategies") or []),
        "source_refs": list(candidate.get("source_refs") or []),
        "cn_seller_gate": _cn_gate(by_field.get("cn_seller_evidence", [])),
        "evidence": evidence_summary,
        "pending_verification": missing,
        "decision_readiness": "ready_for_supply_match" if not missing else "partial",
        "scoring_status": "not_calibrated_not_used_as_global_gate",
        "next_actions": [f"verify:{field}" for field in missing[:3]],
    }


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ContractError("input must be a JSON object")
    action = payload.get("skill_action")
    if action == "status":
        rules = load_rules()
        return {
            "ok": True,
            "skill": "chenyu-jihui",
            "config_revision": rules["config_revision"],
            "actions": ["status", "merge_candidates", "build_opportunity_card"],
        }
    if action == "merge_candidates":
        return {"ok": True, "candidates": merge_candidates(payload.get("candidates") or [])}
    if action == "build_opportunity_card":
        return {
            "ok": True,
            "opportunity_card": build_opportunity_card(
                payload.get("candidate") or {},
                payload.get("evidence") or [],
                payload.get("target_marketplaces"),
            ),
        }
    raise ContractError(f"unknown skill_action: {action}")


def main() -> None:
    try:
        result = handle(json.load(sys.stdin))
    except (json.JSONDecodeError, ContractError, OSError, KeyError, TypeError) as exc:
        result = {"ok": False, "code": "invalid_input", "message": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
