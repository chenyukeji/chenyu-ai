"""Import-backed store, keyword, and Movers & Shakers research with explicit evidence."""
from __future__ import annotations

from datetime import date
import re
from strategy_h import _number

INPUT_HELP = {
    "C": "请提供热词数据：站点、搜索词、搜索量、数据周期、对应 ASIN 和来源；可附上期搜索量。",
    "I": "请提供目标店铺至少两次的商品快照：站点、卖家ID、快照日期、ASIN、来源及快照是否完整。",
    "K": "请提供排名跃升记录：站点、ASIN、榜单类目、当前排名、此前排名、统计窗口小时数、观察时间和来源。",
}


def _snapshot_day(row):
    try:
        return date.fromisoformat(str(row.get("snapshot_date") or "")[:10]).isoformat()
    except ValueError:
        return None


def analyze_evidence(strategy, records, marketplaces, shortlist_limit=20):
    if strategy not in INPUT_HELP:
        raise ValueError("unsupported evidence strategy")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("strategy records must be a list of objects")
    groups, rejected = {}, []
    snapshots = {}
    if strategy == "I":
        for row in records:
            key = (str(row.get("marketplace") or "").upper(), str(row.get("seller_id") or ""))
            day = _snapshot_day(row)
            if all(key) and day and row.get("asin"):
                snapshots.setdefault(key, {}).setdefault(day, []).append(row)
    for row in records:
        market = str(row.get("marketplace") or "").upper()
        asin = str(row.get("asin") or "").upper()
        if market not in marketplaces or not re.fullmatch(r"[A-Z0-9]{10}", asin) or not row.get("source_ref"):
            rejected.append({"asin": asin, "reason": "缺少站点、ASIN 或来源证据"})
            continue
        evidence, score = None, 0
        if strategy == "C":
            volume = _number(row.get("search_volume"))
            previous = _number(row.get("previous_search_volume"))
            if row.get("keyword") and row.get("search_period") and volume is not None and volume > 0:
                growth = (volume / previous - 1) * 100 if previous is not None and previous > 0 and row.get("previous_search_period") else None
                evidence = f"{row['search_period']} 搜索词「{row['keyword']}」搜索量 {volume:g}"
                if growth is not None:
                    evidence += f"，较 {row['previous_search_period']} 变化 {growth:+.1f}%"
                else:
                    evidence += "，缺少可比上期数据，未判断增长"
                score = min(100, 30 + min(volume / 1000, 40) + min(max(growth or 0, 0) / 5, 30))
        elif strategy == "I":
            seller = str(row.get("seller_id") or "")
            periods = snapshots.get((market, seller), {})
            day = _snapshot_day(row)
            if len(periods) >= 2 and day == max(periods):
                first = sorted(periods)[-2]
                previous = periods[first]
                previous_asins = {str(x['asin']).upper() for x in previous}
                if asin not in previous_asins:
                    complete = all(x.get("snapshot_complete") is True for x in previous)
                    evidence = f"店铺 {seller}：{first} → {day} 新发现 ASIN"
                    evidence += "；此前完整快照未出现" if complete else "；此前快照不完整，不能确认实际新上架"
                    score = 70 if complete else 40
        elif strategy == "K":
            current = _number(row.get("current_rank"))
            previous = _number(row.get("previous_rank"))
            hours = _number(row.get("window_hours"))
            if (current is not None and previous is not None and previous > current > 0
                    and hours is not None and hours > 0 and row.get("rank_category") and row.get("observed_at")):
                gain = (previous - current) / previous * 100
                evidence = f"{row['rank_category']}：{hours:g} 小时内排名 {previous:g} → {current:g}，名次提升比例 {gain:.1f}%（非销量增长率）"
                score = min(100, 30 + gain * .7)
        if evidence is None:
            rejected.append({"asin": asin, "reason": INPUT_HELP[strategy] if strategy != "I" else "缺少可比较快照，或商品并非最新快照新发现"})
            continue
        key = (market, asin)
        item = groups.setdefault(key, {**row, "marketplace": market, "asin": asin, "evidence": [], "score": 0, "source_refs": []})
        if evidence not in item["evidence"]:
            item["evidence"].append(evidence)
        item["score"] = max(item["score"], round(score, 1))
        if row["source_ref"] not in item["source_refs"]:
            item["source_refs"].append(row["source_ref"])
    results = sorted(groups.values(), key=lambda row: (-row["score"], row["marketplace"], row["asin"]))
    return {"method": f"strategy_{strategy.lower()}_evidence_priority_v1", "strategy": strategy,
            "count": len(results), "candidates": results[:shortlist_limit], "all_candidates": results,
            "rejected": rejected}


def table_rows(report, name):
    rows = []
    for item in report["candidates"]:
        site, asin = item["marketplace"], item["asin"]
        rows.append({"站点": site, "产品名称": item.get("product_name"), "ASIN": asin,
                     "所在品类": item.get("category_name") or item.get("rank_category"),
                     "预估月销量": item.get("estimated_sales"), "售价（当地币种）": item.get("price"),
                     "Review数量": item.get("review_count"), "图片": item.get("image_url"),
                     "策略": name, "策略证据": "；".join(item["evidence"]), "得分": item["score"],
                     "结论": "优先调研" if item["score"] >= 70 else "继续核验",
                     "理由": "依据所列来源排列调研优先级；仍需结合商品竞争、持续需求和具体产品证据核验。",
                     "来源链接": "；".join(item["source_refs"]),
                     "亚马逊产品链接": item.get("detail_url") or f"https://www.amazon.{'de' if site == 'DE' else 'com'}/dp/{asin}"})
    return rows
