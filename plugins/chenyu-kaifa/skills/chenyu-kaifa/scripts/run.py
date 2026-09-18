"""Executable task-entry helpers for the Chenyu Amazon development workflow (stdlib only)."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parents[1] / "references" / "runtime-rules.json"


class ContractError(ValueError):
    pass


def load_rules() -> dict:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a number")
    return float(value)


def recommend_strategies(task: dict, rules: dict) -> list[str]:
    chosen = list(rules["default_mvp_strategies"])
    signals = {
        "C": bool(task.get("keywords") or task.get("local_keyword")),
        "D": bool(task.get("review_focus") or task.get("reference_product")),
        "F": bool(task.get("component_pool") or task.get("bundle_seed")),
        "H": bool(task.get("target_season")),
        "I": bool(task.get("seller_seed")),
    }
    for sid, enabled in signals.items():
        if enabled and sid not in chosen:
            chosen.append(sid)
    return chosen


def create_task(task: dict | None = None) -> dict:
    rules = load_rules()
    task = dict(task or {})

    allowed_markets = set(rules["sales_marketplaces"])
    markets = task.get("sales_marketplaces") or list(rules["sales_marketplaces"])
    if not isinstance(markets, list) or not markets:
        raise ContractError("sales_marketplaces must be a non-empty list")
    unknown_markets = [m for m in markets if m not in allowed_markets]
    if unknown_markets:
        raise ContractError(f"unsupported sales marketplaces: {unknown_markets}")

    configured_price = rules["target_price_eur"]
    target_price = dict(task.get("target_price_eur") or configured_price)
    low = _number(target_price.get("min"), "target_price_eur.min")
    high = _number(target_price.get("max"), "target_price_eur.max")
    if low > high:
        raise ContractError("target_price_eur.min must be <= max")
    if low < configured_price["min"] or high > configured_price["max"]:
        raise ContractError(
            f"target price must stay within configured €{configured_price['min']}-€{configured_price['max']}"
        )

    configured_cap = float(rules["purchase_packaging_cap_cny"])
    cap = _number(task.get("purchase_packaging_cap_cny", configured_cap), "purchase_packaging_cap_cny")
    if cap <= 0 or cap > configured_cap:
        raise ContractError(
            f"purchase_packaging_cap_cny must be > 0 and <= configured cap {configured_cap}"
        )

    explicit_strategies = task.get("strategy_ids")
    strategy_ids = list(explicit_strategies) if explicit_strategies else recommend_strategies(task, rules)
    registry = rules["strategy_registry"]
    invalid = [sid for sid in strategy_ids if sid not in registry]
    if invalid:
        raise ContractError(f"unknown strategy ids: {invalid}")

    warnings = []
    if task.get("budget_cny") is None:
        warnings.append("budget_cny is pending; do not produce a fixed purchase quantity")
    if not task.get("deadline"):
        warnings.append("deadline is pending; season/lead-time conclusions remain conditional")

    required_outputs = task.get("required_outputs") or [
        "candidate_pool",
        "opportunity_cards",
        "supply_match",
        "economics",
        "decision",
        "development_workbook",
        "trial_card",
    ]

    return {
        "task_id": task.get("task_id") or f"task-{uuid.uuid4().hex[:12]}",
        "sales_marketplaces": markets,
        "category_or_need": task.get("category_or_need"),
        "target_price_eur": {"min": low, "max": high},
        "purchase_packaging_cap_cny": cap,
        "budget_cny": task.get("budget_cny"),
        "deadline": task.get("deadline"),
        "strategy_ids": strategy_ids,
        "strategy_names": {sid: registry[sid]["name"] for sid in strategy_ids},
        "excluded_products": list(task.get("excluded_products") or []),
        "required_outputs": list(required_outputs),
        "rules_snapshot": {
            "config_revision": rules["config_revision"],
            "sales_marketplaces": list(rules["sales_marketplaces"]),
            "target_price_eur": dict(rules["target_price_eur"]),
            "purchase_packaging_cap_cny": configured_cap,
        },
        "warnings": warnings,
    }


def build_plan(task_brief: dict) -> dict:
    return {
        "task_id": task_brief["task_id"],
        "strategy_ids": task_brief["strategy_ids"],
        "phases": [
            {
                "phase": "discovery",
                "owner_skill": "chenyu-jihui",
                "outputs": ["candidate_pool"],
            },
            {
                "phase": "market_validation",
                "owner_skill": "chenyu-jihui",
                "outputs": ["evidence", "opportunity_cards"],
            },
            {
                "phase": "supply_and_economics",
                "owner_skill": "chenyu-kaifa-pingshen",
                "outputs": ["supply_match", "economics", "decision"],
            },
            {
                "phase": "handoff",
                "owner_skill": "chenyu-kaifa-pingshen",
                "outputs": ["development_workbook", "product_master", "handoff", "trial_card"],
            },
        ],
        "blocking_policy": {
            "missing_noncritical_data": "continue_and_mark_pending",
            "missing_hard_gate_data": "gate_unknown_not_pass_or_fail",
            "missing_quote": "research_can_continue_but_cost_gate_cannot_pass",
        },
    }


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ContractError("input must be a JSON object")
    action = payload.get("skill_action")
    if action == "status":
        rules = load_rules()
        return {
            "ok": True,
            "skill": "chenyu-kaifa",
            "config_revision": rules["config_revision"],
            "actions": ["status", "create_task", "plan"],
        }
    if action == "create_task":
        return {"ok": True, "task": create_task(payload.get("task"))}
    if action == "plan":
        brief = payload.get("task_brief")
        if brief is None:
            brief = create_task(payload.get("task"))
        return {"ok": True, "task": brief, "plan": build_plan(brief)}
    raise ContractError(f"unknown skill_action: {action}")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        result = handle(payload)
    except (json.JSONDecodeError, ContractError, OSError, KeyError, TypeError) as exc:
        result = {"ok": False, "code": "invalid_input", "message": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=True, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
