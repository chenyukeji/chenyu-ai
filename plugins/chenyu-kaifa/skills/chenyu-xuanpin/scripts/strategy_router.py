"""Natural-language strategy and category routing for product discovery."""
from __future__ import annotations

import json
from pathlib import Path


REFERENCES_DIR = Path(__file__).resolve().parents[1] / "references"
CATEGORY_PRESETS_PATH = REFERENCES_DIR / "category-presets.json"

STRATEGY_SIGNALS = {
    "A": ("中国卖家", "中国卖家同类", "同类中国卖家", "chinese seller"),
    "B": ("近期需求", "最近需求", "需求趋势", "recent demand", "rising demand"),
    "C": ("关键词", "搜索词", "keyword", "search term"),
    "D": ("差评", "评论痛点", "review痛点", "review pain", "complaint"),
    "E": ("新品榜", "找新品", "新品", "new releases", "new release"),
    "F": ("组合装", "套装", "多件装", "现货组合", "bundle", "multipack"),
    "H": ("旺季", "季节", "圣诞", "万圣节", "复活节", "seasonal", "christmas", "halloween", "q4"),
    "I": ("店铺扩品", "店铺相邻", "这个店铺", "卖家店铺", "storefront", "seller catalog"),
    "J": ("fbm", "近60天", "近 60 天", "最近60天", "最近 60 天"),
}

IMPLEMENTATION_STATUS = {
    "A": "import_ready",
    "B": "planned",
    "C": "planned",
    "D": "planned",
    "E": "available",
    "F": "planned",
    "H": "planned",
    "I": "planned",
    "J": "import_ready",
}


class StrategyRouteError(ValueError):
    pass


def load_category_presets() -> list[dict]:
    return json.loads(CATEGORY_PRESETS_PATH.read_text(encoding="utf-8"))["presets"]


def _normalize_ids(values, registry: dict) -> list[str]:
    if not isinstance(values, list) or not values:
        raise StrategyRouteError("strategy_ids must be a non-empty list")
    result = []
    for value in values:
        strategy_id = str(value).upper()
        if strategy_id not in registry:
            raise StrategyRouteError(f"unknown strategy id: {strategy_id}")
        if strategy_id not in result:
            result.append(strategy_id)
    return result


def _mentioned_markets(text: str) -> list[str]:
    lowered = text.casefold()
    patterns = {
        "US": ("美国", "美国站", "amazon.com", " us ", "美站"),
        "DE": ("德国", "德国站", "amazon.de", " de ", "德站"),
    }
    padded = f" {lowered} "
    return [market for market in ("US", "DE") if any(term in padded for term in patterns[market])]


def resolve_strategy(request: str | None, task: dict, selection: dict | None, rules: dict) -> dict:
    request = str(request or "").strip()
    selection = dict(selection or {})
    registry = rules["strategy_registry"]
    explicit = selection.get("strategy_ids") or task.get("strategy_ids")
    reason_codes = []

    if explicit:
        strategy_ids = _normalize_ids(explicit, registry)
        source = "explicit"
        confidence = "high"
        reason_codes.append("EXPLICIT_STRATEGY_SELECTION")
    else:
        lowered = request.casefold()
        matches = []
        for strategy_id, signals in STRATEGY_SIGNALS.items():
            positions = [lowered.find(signal.casefold()) for signal in signals if signal.casefold() in lowered]
            if positions:
                matches.append((min(positions), strategy_id))
        matches.sort()
        strategy_ids = [strategy_id for _, strategy_id in matches]
        if strategy_ids:
            source = "inferred"
            confidence = "high" if len(strategy_ids) == 1 else "medium"
            reason_codes.extend(f"REQUEST_SIGNAL_{strategy_id}" for strategy_id in strategy_ids)
        else:
            strategy_ids = ["E"]
            source = "default"
            confidence = "default"
            reason_codes.append("NO_STRATEGY_SIGNAL_USE_DEFAULT_NEW_RELEASES")

    configured_markets = (
        selection.get("source_marketplaces")
        or task.get("source_marketplaces")
        or task.get("discovery_marketplaces")
    )
    if configured_markets:
        if not isinstance(configured_markets, list):
            raise StrategyRouteError("source_marketplaces must be a list")
        source_markets = [str(value).upper() for value in configured_markets]
        selection_market_source = "explicit"
    else:
        mentioned = _mentioned_markets(request)
        source_markets = mentioned or list(rules["discovery_marketplaces"])
        selection_market_source = "inferred" if mentioned else "default"
    unsupported = [market for market in source_markets if market not in rules["discovery_marketplaces"]]
    if unsupported:
        raise StrategyRouteError(f"unsupported discovery marketplaces: {unsupported}")

    primary = strategy_ids[0]
    return {
        "mode": selection.get("mode") or ("manual" if source == "explicit" else "auto"),
        "strategy_ids": strategy_ids,
        "primary_strategy": primary,
        "supporting_strategies": strategy_ids[1:],
        "selection_source": source,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "source_marketplaces": source_markets,
        "source_marketplaces_selection": selection_market_source,
        "strategies": [
            {
                "strategy_id": strategy_id,
                "name": registry[strategy_id]["name"],
                "implementation_status": IMPLEMENTATION_STATUS[strategy_id],
                "role": "primary" if strategy_id == primary else "supporting",
            }
            for strategy_id in strategy_ids
        ],
    }


def resolve_category(request: str | None, task: dict) -> dict:
    request = str(request or "").strip()
    if "amazon_new_releases" in task or "category_or_need" in task:
        raise StrategyRouteError("类目参数已更新，请使用 task.categories 重新提交")
    presets = load_category_presets()
    categories = task.get("categories")
    source = "custom"
    if categories is None:
        matches = [preset for preset in presets if any(
            keyword.casefold() in request.casefold() for keyword in preset["keywords"]
        )]
        if matches:
            categories = [{"name": item["category_normalized"],
                           "amazon_new_releases": item["amazon_new_releases"]} for item in matches]
            source = "preset"
        else:
            categories = [{"name": request, "amazon_new_releases": {}}] if request else []
            source = "request_text"
    if not isinstance(categories, list) or not categories:
        raise StrategyRouteError("请提供类目名称或非空的 task.categories")
    resolved = []
    for item in categories:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise StrategyRouteError("task.categories 每项必须有非空 name")
        name = item["name"].strip()
        urls = item.get("amazon_new_releases")
        if urls is None:
            preset = next((preset for preset in presets if name.casefold() in
                           [preset["category_normalized"].casefold(), *(word.casefold() for word in preset["keywords"])]), None)
            urls = dict(preset["amazon_new_releases"]) if preset else {}
        if not isinstance(urls, dict):
            raise StrategyRouteError("amazon_new_releases 必须是站点到 URL 的映射")
        resolved.append({"name": name, "amazon_new_releases": urls})
    return {
        "status": "resolved" if all(c["amazon_new_releases"] for c in resolved) else "unmapped",
        "selection_source": source,
        "category_original": request,
        "category_normalized": "、".join(c["name"] for c in resolved),
        "categories": resolved,
    }


def list_strategies(rules: dict) -> list[dict]:
    return [
        {
            "strategy_id": strategy_id,
            "name": config["name"],
            "role": config["role"],
            "phase": config["phase"],
            "implementation_status": IMPLEMENTATION_STATUS[strategy_id],
        }
        for strategy_id, config in rules["strategy_registry"].items()
    ]
