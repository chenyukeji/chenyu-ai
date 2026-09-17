from __future__ import annotations

from typing import Any

from .compliance import assess_compliance
from .io_utils import clamp
from .models import Candidate
from .profit import calculate_profit


WEIGHTS = {
    "market_demand": 20,
    "new_product_success": 12,
    "competition_opportunity": 15,
    "differentiation": 15,
    "profit": 18,
    "supply_chain": 10,
    "compliance": 10,
}


def evaluate_product(case: dict[str, Any]) -> dict[str, Any]:
    candidate = Candidate.from_dict(case["candidate"])
    market = case.get("market", {})
    profit = case.get("profit") or calculate_profit(case["profit_inputs"])
    compliance = case.get("compliance") or assess_compliance(
        case.get("compliance_profile", {}), case.get("marketplace") or candidate.marketplace or "EU"
    )

    raw_scores = {
        "market_demand": _five(market.get("demand", 0)),
        "new_product_success": _five(market.get("new_product_success", 0)),
        "competition_opportunity": _five(market.get("competition_opportunity", 0)),
        "differentiation": _five(case.get("development_plan", {}).get("differentiation_score", 0)),
        "profit": _profit_score(profit),
        "supply_chain": _five(case.get("supply_chain", {}).get("score", 0)),
        "compliance": {"low": 5.0, "medium": 2.5, "high": 0.0}.get(compliance["risk"], 0.0),
    }
    weighted = {name: round(score / 5 * WEIGHTS[name], 2) for name, score in raw_scores.items()}
    total = round(sum(weighted.values()), 1)

    hard_gates: list[str] = []
    conservative_margin = float(profit["conservative"]["net_margin"])
    if compliance.get("hard_gate"):
        hard_gates.append("High compliance risk or missing regulated-product evidence")
    if conservative_margin < float(case.get("minimum_conservative_margin", 0.08)):
        hard_gates.append("Conservative net margin is below the minimum gate")
    if not case.get("development_plan", {}).get("core_differentiation"):
        hard_gates.append("Core differentiation is not defined")

    if hard_gates or total < 55:
        decision = "NO_GO"
    elif total < 75:
        decision = "WATCH"
    else:
        decision = "GO"

    return {
        "schema_version": "1.0",
        "product": candidate.product_type,
        "candidate": candidate.to_dict(),
        "decision": decision,
        "development_score": total,
        "scores_0_to_5": {name: round(value, 2) for name, value in raw_scores.items()},
        "weighted_scores": weighted,
        "recommended_marketplaces": case.get("recommended_marketplaces", [candidate.marketplace] if candidate.marketplace else []),
        "recommended_price": case.get("recommended_price", {}),
        "target_purchase_price_cny": case.get("target_purchase_price_cny"),
        "development_plan": case.get("development_plan", {}),
        "supply_chain": case.get("supply_chain", {}),
        "profit": profit,
        "compliance": compliance,
        "hard_gates": hard_gates,
        "largest_risks": case.get("largest_risks", []),
        "evidence_notes": case.get("evidence_notes", []),
    }


def _five(value: Any) -> float:
    return clamp(float(value), 0.0, 5.0)


def _profit_score(profit: dict[str, Any]) -> float:
    normal = float(profit["normal"]["net_margin"])
    conservative = float(profit["conservative"]["net_margin"])
    blended = normal * 0.6 + conservative * 0.4
    return clamp(blended / 0.25 * 5.0, 0.0, 5.0)

