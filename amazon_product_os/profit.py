from __future__ import annotations

from copy import deepcopy
from typing import Any

from .io_utils import clamp


def calculate_profit(inputs: dict[str, Any]) -> dict[str, Any]:
    """Calculate normal and conservative unit economics for VAT-inclusive EU/UK prices."""
    required = ["sale_price", "vat_rate", "commission_rate", "fba_fee", "purchase_cost_cny", "cny_per_currency"]
    missing = [key for key in required if key not in inputs]
    if missing:
        raise ValueError(f"Missing profit inputs: {', '.join(missing)}")
    normal = _scenario(inputs)
    conservative_inputs = deepcopy(inputs)
    conservative = dict(inputs.get("conservative", {}))
    conservative_inputs["sale_price"] = conservative.get("sale_price", inputs["sale_price"] * 0.95)
    conservative_inputs["purchase_cost_cny"] = conservative.get("purchase_cost_cny", inputs["purchase_cost_cny"] * 1.1)
    conservative_inputs["first_mile"] = conservative.get("first_mile", inputs.get("first_mile", 0) * 1.15)
    conservative_inputs["ad_rate"] = conservative.get("ad_rate", max(inputs.get("ad_rate", 0), inputs.get("ad_rate", 0) * 1.25))
    conservative_inputs["return_reserve_rate"] = conservative.get(
        "return_reserve_rate", max(inputs.get("return_reserve_rate", 0), inputs.get("return_reserve_rate", 0) * 1.25)
    )
    conservative_result = _scenario(conservative_inputs)
    target_margin = float(inputs.get("target_margin", 0.2))
    return {
        "currency": inputs.get("currency", "EUR"),
        "normal": normal,
        "conservative": conservative_result,
        "target_margin": target_margin,
        "meets_target": normal["net_margin"] >= target_margin and conservative_result["net_margin"] >= target_margin * 0.65,
        "notes": [
            "Sale price is treated as VAT-inclusive.",
            "Commission and percentage reserves are calculated on the displayed sale price.",
            "Confirm FBA fees with the current Amazon fee preview before committing inventory.",
        ],
    }


def _scenario(inputs: dict[str, Any]) -> dict[str, Any]:
    price = float(inputs["sale_price"])
    vat_rate = float(inputs["vat_rate"])
    commission_rate = float(inputs["commission_rate"])
    exchange_rate = float(inputs["cny_per_currency"])
    if price <= 0 or exchange_rate <= 0:
        raise ValueError("sale_price and cny_per_currency must be positive")
    net_revenue = price / (1 + vat_rate)
    vat = price - net_revenue
    purchase = float(inputs["purchase_cost_cny"]) / exchange_rate
    components = {
        "vat": vat,
        "amazon_commission": price * commission_rate,
        "fba_fee": float(inputs["fba_fee"]),
        "purchase_cost": purchase,
        "domestic_logistics": float(inputs.get("domestic_logistics_cny", 0)) / exchange_rate,
        "first_mile": float(inputs.get("first_mile", 0)),
        "packaging": float(inputs.get("packaging_cny", 0)) / exchange_rate,
        "advertising": price * float(inputs.get("ad_rate", 0)),
        "return_reserve": price * float(inputs.get("return_reserve_rate", 0)),
        "other": float(inputs.get("other_cost", 0)),
    }
    costs_excluding_vat = sum(value for key, value in components.items() if key != "vat")
    profit = net_revenue - costs_excluding_vat
    margin = profit / price
    return {
        "sale_price": round(price, 2),
        "net_revenue_ex_vat": round(net_revenue, 2),
        "costs": {key: round(value, 2) for key, value in components.items()},
        "net_profit": round(profit, 2),
        "net_margin": round(clamp(margin, -1.0, 1.0), 4),
        "roi_on_landed_product_cost": round(profit / max(0.01, purchase + components["domestic_logistics"] + components["first_mile"] + components["packaging"]), 4),
    }

