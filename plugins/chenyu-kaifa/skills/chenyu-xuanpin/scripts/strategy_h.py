"""Evidence-based seasonal candidates from SellerSprite historical monthly sales surges."""
from __future__ import annotations

from datetime import date
from math import isfinite
import re


class SeasonalStrategyError(ValueError):
    pass


def target_months(as_of_date=None, following_months=2):
    if type(following_months) is not int or following_months not in (2, 3):
        raise SeasonalStrategyError("h_following_months 必须为 2 或 3")
    today = date.fromisoformat(str(as_of_date)[:10]) if as_of_date else date.today()
    start = (today.year - 1) * 12 + today.month - 1
    return [f"{(start + offset) // 12:04d}-{(start + offset) % 12 + 1:02d}"
            for offset in range(following_months + 1)]


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(",", "").replace("%", ""))
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def analyze_monthly_surge(records, months, marketplaces, *, min_sales=300, min_growth=10,
                          shortlist_limit=20):
    """Keep historical monthly values separate from present-day sales estimates."""
    if not months or not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise SeasonalStrategyError("H 需要目标月份和卖家精灵月度榜单记录")
    if not isfinite(min_sales) or not isfinite(min_growth) or min_sales < 1 or min_growth < 0:
        raise SeasonalStrategyError("历史销量和增长阈值不合法")
    allowed = set(months)
    markets = set(marketplaces)
    groups = {}
    rejected = []
    for row in records:
        market = str(row.get("marketplace") or "").upper()
        asin = str(row.get("asin") or "").upper()
        month = str(row.get("history_month") or row.get("month") or "")[:7]
        sales = _number(row.get("estimated_sales"))
        growth = _number(row.get("sales_growth_percent"))
        reason = None
        if market not in markets or month not in allowed or not re.fullmatch(r"[A-Z0-9]{10}", asin):
            reason = "站点、月份或 ASIN 不属于本次范围"
        elif not row.get("source_ref"):
            reason = "缺少历史数据来源"
        elif sales is None or growth is None:
            reason = "缺少可核验的历史月销量或环比增长率"
        elif sales < min_sales or growth < min_growth:
            reason = "未达到销量飙升榜阈值"
        if reason:
            rejected.append({"marketplace": market, "asin": asin, "month": month, "reason": reason})
            continue
        key = (market, asin)
        group = groups.setdefault(key, {"marketplace": market, "asin": asin, "months": {}, "source_refs": []})
        evidence = {"month": month, "estimated_sales": sales, "sales_growth_percent": growth,
                    "source_ref": row.get("source_ref"), "product_name": row.get("product_name")}
        if month not in group["months"] or sales > group["months"][month]["estimated_sales"]:
            group["months"][month] = evidence
        ref = row.get("source_ref")
        if ref and ref not in group["source_refs"]:
            group["source_refs"].append(ref)
        for field in ("product_name", "category_name", "image_url", "detail_url", "price", "currency", "review_count", "bsr"):
            if row.get(field) is not None and group.get(field) is None:
                group[field] = row[field]
    candidates = []
    for group in groups.values():
        evidence = [group["months"][month] for month in months if month in group["months"]]
        count = len(evidence)
        max_growth = max(item["sales_growth_percent"] for item in evidence)
        peak_sales = max(item["estimated_sales"] for item in evidence)
        score = min(100, round(25 + 15 * count + min(max_growth, 200) * .15 + min(peak_sales, 2000) * .01))
        candidates.append({**{k: v for k, v in group.items() if k != "months"},
                           "monthly_evidence": evidence, "hit_months": count,
                           "peak_sales": peak_sales, "max_growth_percent": max_growth,
                           "score": score, "conclusion": "季节性候选（待跨年复核）",
                           "reason": f"去年窗口 {count}/{len(months)} 个月进入销量飙升榜；命中月最高销量 {peak_sales:g}，最大环比增幅 {max_growth:g}%。仅有一年的窗口记录，需核查前一年及今年走势。"})
    candidates.sort(key=lambda item: (-item["score"], -item["hit_months"], -item["peak_sales"], item["asin"]))
    return {"method": "seller_sprite_historical_monthly_surge_v1", "months": months,
            "thresholds": {"min_sales": min_sales, "min_growth_percent": min_growth},
            "count": len(candidates), "rejected": rejected,
            "candidates": candidates[:shortlist_limit], "all_candidates": candidates}


def table_rows(report):
    rows = []
    for item in report["candidates"]:
        site = item["marketplace"]
        asin = item["asin"]
        months = item["monthly_evidence"]
        rows.append({"站点": site, "产品名称": item.get("product_name"), "ASIN": asin,
                     "所在品类": item.get("category_name"),
                     "历史命中月份": "、".join(x["month"] for x in months),
                     "月度销量与增长": "；".join(f"{x['month']}：{x['estimated_sales']:g} 件，环比 +{x['sales_growth_percent']:g}%" for x in months),
                     "命中月份最高月销量": item["peak_sales"], "最大环比增长率": item["max_growth_percent"],
                     "售价（当地币种）": item.get("price"), "Review数量": item.get("review_count"),
                     "大品类排名": item.get("bsr"), "图片": item.get("image_url"),
                     "亚马逊产品链接": item.get("detail_url") or f"https://www.amazon.{'de' if site == 'DE' else 'com'}/dp/{asin}",
                     "得分": item["score"], "结论": item["conclusion"], "理由": item["reason"],
                     "来源链接": "；".join(item["source_refs"])})
    return rows
