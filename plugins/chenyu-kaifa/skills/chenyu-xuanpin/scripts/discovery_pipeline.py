"""Candidate normalization, scoring and table rows for the single discovery skill."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime


class DiscoveryError(ValueError):
    pass


LISTING_FIELDS = (
    "marketplace",
    "asin",
    "parent_asin",
    "product_name",
    "price",
    "currency",
    "estimated_sales",
    "estimated_revenue",
    "new_release_rank",
    "ranking_type",
    "review_count",
    "rating",
    "source_available_date",
    "listing_date",
    "bsr",
    "category_name",
    "category_node",
    "fulfillment",
    "seller_location",
    "image_url",
    "detail_url",
    "source_ref",
    "observed_at",
    "enrichment_status",
    "product_advantages",
    "product_disadvantages",
    "review_pain_points",
    "saleable_window",
    "peak_months",
    "seasonality",
    "history_signals",
    "history_first_seen",
    "history_last_seen",
    "history_days_present",
    "history_snapshots_available",
    "history_consecutive_snapshots",
    "history_repeat_rate",
    "history_period_rank_change",
    "history_rank_velocity",
    "history_rank_consistency",
    "history_rank_history",
)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _stable_id(marketplace: str, identity: str) -> str:
    digest = hashlib.sha1(f"{marketplace}|{identity}".encode("utf-8")).hexdigest()[:12]
    return f"cand-{digest}"


def merge_candidates(records: list[dict]) -> list[dict]:
    if not isinstance(records, list):
        raise DiscoveryError("records must be a list")
    groups = {}
    for row in records:
        if not isinstance(row, dict):
            raise DiscoveryError("each record must be an object")
        market = str(row.get("marketplace") or row.get("source_market") or "").upper()
        asin = str(row.get("asin") or "").upper()
        parent = str(row.get("parent_asin") or "").upper()
        identity = parent or asin
        if not market or not identity:
            continue
        key = (market, identity)
        candidate = groups.setdefault(
            key,
            {
                "candidate_id": row.get("candidate_id") or _stable_id(market, identity),
                "product_name": row.get("product_name") or row.get("product_name_normalized"),
                "source_strategies": [],
                "source_refs": [],
                "marketplace_listings": [],
                "research_status": "DISCOVERED",
            },
        )
        if not candidate.get("product_name") and row.get("product_name"):
            candidate["product_name"] = row["product_name"]
        strategies = row.get("source_strategies") or [row.get("source_strategy") or "E"]
        for strategy_id in strategies:
            if strategy_id and strategy_id not in candidate["source_strategies"]:
                candidate["source_strategies"].append(strategy_id)
        refs = row.get("source_refs") or [row.get("source_ref")]
        for ref in refs:
            if ref and ref not in candidate["source_refs"]:
                candidate["source_refs"].append(ref)
        listing = {field: row.get(field) for field in LISTING_FIELDS if row.get(field) is not None}
        listing["marketplace"] = market
        listing["asin"] = asin or parent
        existing_index = next(
            (
                index
                for index, current in enumerate(candidate["marketplace_listings"])
                if current.get("marketplace") == market and current.get("asin") == listing.get("asin")
            ),
            None,
        )
        if existing_index is None:
            candidate["marketplace_listings"].append(listing)
        else:
            candidate["marketplace_listings"][existing_index].update(listing)
    return list(groups.values())


def _days_old(value, as_of_date=None):
    if not value:
        return None
    try:
        listed = date.fromisoformat(str(value)[:10])
        observed = date.fromisoformat(str(as_of_date)[:10]) if as_of_date else datetime.now().date()
        return max(0, (observed - listed).days)
    except ValueError:
        return None


def _points_by_threshold(value, bands):
    if value is None:
        return 0
    for maximum, points in bands:
        if value <= maximum:
            return points
    return bands[-1][1]


def _rank_points(value):
    return _points_by_threshold(value, ((10, 30), (25, 26), (50, 20), (100, 12), (float("inf"), 4)))


def _sales_points(value):
    if value is None or value <= 0:
        return 0
    if value >= 500:
        return 25
    if value >= 200:
        return 22
    if value >= 100:
        return 18
    if value >= 50:
        return 12
    return 6


def _recency_points(value):
    return _points_by_threshold(value, ((30, 15), (60, 13), (120, 8), (365, 4), (float("inf"), 1)))


def _review_points(value):
    return _points_by_threshold(value, ((30, 10), (100, 8), (300, 5), (float("inf"), 2)))


def _price_points(value):
    if value is None:
        return 0
    if 5 <= value <= 20:
        return 10
    if 3 <= value <= 25:
        return 6
    return 2


def _best_listing(candidate: dict) -> dict:
    listings = candidate.get("marketplace_listings") or []
    return min(
        listings,
        key=lambda row: (
            _number(row.get("new_release_rank")) or float("inf"),
            -(_number(row.get("estimated_sales")) or 0),
        ),
        default={},
    )


def _as_phrases(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("|", "；").split("；") if part.strip()]


def _dedupe(values) -> list[str]:
    output = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in output:
            output.append(value)
    return output


def _contains_chinese(value) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def _product_summary_zh(candidate: dict) -> str:
    text = str(candidate.get("product_name") or "").casefold()
    themes = []
    theme_rules = (
        (("halloween", "ghost", "scream", "万圣节"), "万圣节"),
        (("christmas", "xmas", "advent", "圣诞"), "圣诞"),
        (("birthday", "geburtstag", "生日"), "生日"),
        (("wedding", "hochzeit", "婚礼"), "婚礼"),
        (("graduation", "毕业"), "毕业季"),
        (("baby shower", "婴儿派对"), "迎婴派对"),
        (("unicorn", "einhorn", "独角兽"), "独角兽主题"),
        (("dinosaur", "dino", "恐龙"), "恐龙主题"),
        (("anime", "cartoon", "卡通", "动漫"), "卡通主题"),
    )
    for keywords, label in theme_rules:
        if any(keyword in text for keyword in keywords):
            themes.append(label)
    type_rules = (
        (("cake topper", "tortendeko", "蛋糕插牌"), "蛋糕装饰插牌"),
        (("tablecloth", "table cover", "tischdecke", "桌布"), "派对桌布"),
        (("sticker book", "sticker", "贴纸"), "儿童贴纸活动套装"),
        (("balloon arch", "balloon garland", "气球拱门"), "气球拱门套装"),
        (("balloon", "luftballon", "气球"), "气球装饰套装"),
        (("mask", "maske", "面具"), "角色面具"),
        (("bracelet", "armbänder", "手环"), "儿童主题手环"),
        (("fidget", "解压"), "儿童解压小玩具"),
        (("yoyo", "yo yo", "yo-yo", "溜溜球"), "儿童溜溜球回礼套装"),
        (("gift bag", "party bag", "treat bag", "礼品袋"), "派对礼品袋"),
        (("banner", "girlande", "横幅"), "派对横幅装饰套装"),
        (("candle", "kerze", "蜡烛"), "派对蜡烛"),
        (("pinata", "皮纳塔"), "派对皮纳塔用品"),
        (("giveaway", "mitgebsel", "party favor", "回礼"), "儿童派对回礼套装"),
        (("decoration", "deko", "party supplies", "派对用品"), "派对装饰套装"),
    )
    product_label = "派对用品"
    for keywords, label in type_rules:
        if any(keyword in text for keyword in keywords):
            product_label = label
            break
    count_match = re.search(r"(?<!\d)(\d{1,3})\s*(?:pcs|pieces|stück|pack|count|件|个)", text)
    count = f"{count_match.group(1)}件装" if count_match else None
    return "·".join(_dedupe(themes + [product_label, count]))


def _category_display_zh(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if _contains_chinese(text):
        return text
    lowered = text.casefold()
    if "party" in lowered or "partybedarf" in lowered or "partyzubehör" in lowered:
        return "玩具 > 派对用品"
    if "toy" in lowered or "spielzeug" in lowered:
        return "玩具"
    return "派对用品"


def _conclusion(score: int, missing_data: list[str], rank=None, sales=None, reviews=None) -> str:
    labels = ["🔴 不建议", "🟡 观察", "🟡 偏弱", "🟢 条件开", "🟢 开", "🟢 强开"]
    if score >= 85 and len(missing_data) <= 1:
        base_index = 5
    elif score >= 75:
        base_index = 4
    elif score >= 65:
        base_index = 3
    elif score >= 50:
        base_index = 2
    elif score >= 35:
        base_index = 1
    else:
        base_index = 0

    cap_index = 5
    if len(missing_data) >= 2:
        cap_index = min(cap_index, 1)
    elif missing_data:
        cap_index = min(cap_index, 3)
    if reviews is not None and reviews > 300:
        cap_index = min(cap_index, 3)
    elif reviews is not None and reviews > 100:
        cap_index = min(cap_index, 4)
    if (sales is not None and sales < 50) or (rank is not None and rank > 100):
        cap_index = min(cap_index, 2)
    return labels[min(base_index, cap_index)]


def _saleable_window(candidate: dict, listing: dict) -> str:
    explicit = listing.get("saleable_window") or listing.get("peak_months") or listing.get("seasonality")
    if explicit:
        return str(explicit).strip()
    text = " ".join(
        str(value or "")
        for value in (candidate.get("product_name"), listing.get("category_name"), listing.get("category_node"))
    ).casefold()
    seasonal_windows = (
        (("halloween", "万圣节", "scream", "ghost"), "8–10月（万圣节季）"),
        (("christmas", "xmas", "圣诞", "advent"), "10–12月（圣诞季）"),
        (("easter", "复活节"), "2–4月（复活节季）"),
        (("valentine", "情人节"), "1–2月（情人节季）"),
        (("graduation", "毕业"), "4–7月（毕业季）"),
        (("back to school", "einschulung", "开学", "schultüte"), "7–9月（开学季）"),
        (("oktoberfest", "啤酒节"), "8–10月（啤酒节季）"),
        (("summer", "beach", "pool", "夏季", "沙滩"), "5–8月（夏季）"),
    )
    for keywords, window in seasonal_windows:
        if any(keyword in text for keyword in keywords):
            return window
    if any(keyword in text for keyword in ("birthday", "geburtstag", "party", "婚礼", "wedding", "派对")):
        return "全年可售（生日、婚礼及聚会季需求更高）"
    return "全年可售（需结合历史月销趋势复核旺淡季）"


def _product_advantages(candidate: dict, listing: dict) -> list[str]:
    explicit = [value for value in _as_phrases(listing.get("product_advantages")) if _contains_chinese(value)]
    text = str(candidate.get("product_name") or "").casefold()
    inferred = []
    if any(keyword in text for keyword in ("reusable", "wiederverwend", "可重复")):
        inferred.append("可重复使用")
    if any(keyword in text for keyword in ("set", "kit", "pack", "pcs", "stück", "套装", "组合")):
        inferred.append("套装或多件装，派对场景完整")
    if any(keyword in text for keyword in ("led", "light", "leucht", "发光")):
        inferred.append("带灯光或互动效果")
    if any(keyword in text for keyword in ("theme", "themed", "motto", "主题")):
        inferred.append("主题属性明确，适合场景化陈列")
    if any(keyword in text for keyword in ("disposable", "einweg", "一次性")):
        inferred.append("使用门槛低，适合聚会即时需求")
    return _dedupe(explicit + inferred) or ["使用场景明确，适合作为派对用品候选"]


def _product_disadvantages(candidate: dict, listing: dict) -> list[str]:
    explicit = [
        value
        for value in _as_phrases(listing.get("product_disadvantages")) + _as_phrases(listing.get("review_pain_points"))
        if _contains_chinese(value)
    ]
    text = str(candidate.get("product_name") or "").casefold()
    inferred = []
    if any(keyword in text for keyword in ("balloon", "luftballon", "气球")):
        inferred.extend(("存在破损、漏气和色差风险", "组装布置较耗时"))
    if any(keyword in text for keyword in ("tablecloth", "table cover", "tischdecke", "桌布")):
        inferred.extend(("尺寸适配要求高", "薄料可能出现易撕裂或透底问题"))
    if any(keyword in text for keyword in ("mask", "maske", "costume", "面具")):
        inferred.extend(("佩戴尺寸和舒适度存在个体差异", "长时间佩戴可能闷热或有材料气味"))
    if any(keyword in text for keyword in ("sticker", "贴纸")):
        inferred.extend(("粘性和可重复使用效果容易影响评价", "小尺寸图案的印刷清晰度需验证"))
    if any(keyword in text for keyword in ("cake topper", "tortendeko", "蛋糕插牌")):
        inferred.extend(("尺寸可能与蛋糕不匹配", "食品接触材质和边缘安全需核查"))
    if any(keyword in text for keyword in ("latex", "乳胶")):
        inferred.append("乳胶气味和过敏敏感问题需关注")
    if any(keyword in text for keyword in ("fidget", "giveaway", "mitgebsel", "small toy", "小玩具")):
        inferred.extend(("小零件存在年龄适用和安全提示要求", "多件装的一致性和耐用性容易产生差评"))
    if any(keyword in text for keyword in ("bracelet", "armbänder", "手环")):
        inferred.append("尺寸、印刷耐久和皮肤接触舒适度需验证")
    if any(keyword in text for keyword in ("decoration", "deko", "party supplies", "派对用品")) and not inferred:
        inferred.extend(("同类产品差异化有限", "配件完整性和实物质感需通过样品验证"))
    return _dedupe(explicit + inferred) or ["同质化风险较高；材质、尺寸和耐用性需通过评论与样品验证"]


def _demand_signal(rank, sales, history_signal=None) -> str:
    evidence = []
    if rank is not None:
        evidence.append(f"新品榜第{int(rank)}名")
    if sales is not None:
        evidence.append(f"预估月销量{int(sales)}")
    if history_signal:
        evidence.append(str(history_signal))
    if rank is None or sales is None:
        level = "证据不足"
    elif rank <= 25 and sales >= 200:
        level = "强"
    elif rank <= 50 and sales >= 100:
        level = "中强"
    elif rank <= 100 or sales >= 50:
        level = "中等"
    else:
        level = "偏弱"
    return f"市场信号：{'，'.join(evidence) if evidence else '无有效排名和销量'}，需求判断为{level}"


def _history_signal_text(listing: dict) -> str | None:
    signals = set(listing.get("history_signals") or [])
    evidence = []
    if "NEW" in signals:
        first_seen = listing.get("history_first_seen")
        evidence.append(f"数据库首次出现{('于' + str(first_seen)) if first_seen else ''}")
    if "REPEAT" in signals:
        present = listing.get("history_days_present")
        available = listing.get("history_snapshots_available")
        consecutive = listing.get("history_consecutive_snapshots")
        if present is not None and available is not None:
            text = f"窗口内出现{present}/{available}个快照"
            if consecutive:
                text += f"，最近连续{consecutive}次"
            evidence.append(text)
    if "RISING" in signals:
        change = listing.get("history_period_rank_change")
        consistency = listing.get("history_rank_consistency")
        text = f"窗口排名净提升{int(change)}名" if change is not None else "窗口排名上升"
        if consistency is not None:
            text += f"，上升步占比{float(consistency):.0%}"
        evidence.append(text)
    return "；".join(evidence) or None


def _competition_signal(reviews, bsr) -> str:
    evidence = []
    if reviews is not None:
        evidence.append(f"Review {int(reviews)}")
        level = "低" if reviews <= 30 else "中" if reviews <= 100 else "较高" if reviews <= 300 else "高"
    else:
        level = "证据不足"
    if bsr is not None:
        evidence.append(f"大类BSR {int(bsr)}")
    return f"竞争门槛：{'，'.join(evidence) if evidence else '无有效Review和BSR'}，门槛判断为{level}"


def _freshness_and_price_signal(days, price, currency) -> str:
    evidence = []
    if days is not None:
        freshness = "新品窗口" if days <= 60 else "近期上架" if days <= 120 else "非新品窗口"
        evidence.append(f"上架约{int(days)}天，{freshness}")
    else:
        evidence.append("上架日期缺失")
    if price is not None:
        currency_name = {"USD": "美元", "EUR": "欧元"}.get(str(currency or "").upper(), "当地币种")
        price_fit = "核心价格带" if 5 <= price <= 20 else "邻近价格带" if 3 <= price <= 25 else "偏离当前价格带"
        evidence.append(f"售价{price:g}{currency_name}，{price_fit}")
    else:
        evidence.append("售价缺失")
    return "新品与价格：" + "，".join(evidence)


def _next_step(conclusion: str, missing_data: list[str]) -> str:
    label = conclusion.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "")
    if missing_data:
        return "下一步：先补齐缺失数据，再核验供应链、利润和儿童用品合规"
    if label in {"强开", "开"}:
        return "下一步：优先进入供应链、利润、知识产权和儿童用品合规核验"
    if label == "条件开":
        return "下一步：先验证差异化与样品质量，再核验利润和合规"
    if label in {"偏弱", "观察"}:
        return "下一步：继续观察需求或补充差异化证据，暂不直接进入采购"
    return "下一步：暂缓，除非获得新的需求、差异化或成本优势证据"


def _standard_decision_reason(
    *,
    rank,
    sales,
    reviews,
    bsr,
    days,
    price,
    currency,
    saleable_window: str,
    product_disadvantages: list[str],
    missing_data: list[str],
    conclusion: str,
    score: int,
    history_signal=None,
) -> str:
    completeness = 5 - len(missing_data)
    sections = [
        _demand_signal(rank, sales, history_signal),
        _competition_signal(reviews, bsr),
        _freshness_and_price_signal(days, price, currency),
        f"销售周期：{saleable_window}",
        "主要风险：" + "、".join(product_disadvantages[:2]),
        f"数据与评分：{completeness}/5，综合{score}分，结论{conclusion.replace('🟢 ', '').replace('🟡 ', '').replace('🔴 ', '')}"
        + (f"，缺失{'、'.join(missing_data)}" if missing_data else "，关键字段完整"),
        _next_step(conclusion, missing_data),
    ]
    return "。".join(sections) + "。"


def score_candidates(candidates: list[dict], shortlist_limit=20, as_of_date=None) -> dict:
    if isinstance(shortlist_limit, bool) or not isinstance(shortlist_limit, int) or shortlist_limit < 1:
        raise DiscoveryError("shortlist_limit must be an integer >= 1")
    results = []
    for candidate in candidates:
        listing = _best_listing(candidate)
        rank = _number(listing.get("new_release_rank"))
        sales = _number(listing.get("estimated_sales"))
        reviews = _number(listing.get("review_count"))
        price = _number(listing.get("price"))
        listed_at = listing.get("source_available_date") or listing.get("listing_date")
        days = _days_old(listed_at, as_of_date)
        completeness = sum(value is not None for value in (rank, sales, reviews, price, days)) * 2
        components = {
            "新品榜排名": _rank_points(rank),
            "预估月销量": _sales_points(sales),
            "上架新鲜度": _recency_points(days),
            "Review竞争度": _review_points(reviews),
            "价格带适配": _price_points(price),
            "数据完整度": completeness,
        }
        score = int(sum(components.values()))
        positives = []
        market_risks = []
        missing_data = []
        if rank is not None:
            positives.append(f"新品榜第{int(rank)}名")
        else:
            missing_data.append("新品榜排名")
        if sales is not None:
            positives.append(f"预估月销量{int(sales)}")
        else:
            missing_data.append("预估月销量")
        if days is not None:
            positives.append(f"上架约{int(days)}天")
        else:
            missing_data.append("可靠上架日期")
        if reviews is not None:
            positives.append(f"Review {int(reviews)}")
            if reviews > 300:
                market_risks.append("Review壁垒较高")
        else:
            missing_data.append("Review数量")
        if price is not None:
            currency = {"USD": "美元", "EUR": "欧元"}.get(str(listing.get("currency") or "").upper(), "当地币种")
            positives.append(f"售价{price:g}{currency}")
        else:
            missing_data.append("售价")

        product_advantages = _product_advantages(candidate, listing)
        product_disadvantages = _product_disadvantages(candidate, listing)

        saleable_window = _saleable_window(candidate, listing)
        conclusion = _conclusion(score, missing_data, rank, sales, reviews)
        decision_reason = _standard_decision_reason(
            rank=rank,
            sales=sales,
            reviews=reviews,
            bsr=_number(listing.get("bsr")),
            days=days,
            price=price,
            currency=listing.get("currency"),
            saleable_window=saleable_window,
            product_disadvantages=product_disadvantages,
            missing_data=missing_data,
            conclusion=conclusion,
            score=score,
            history_signal=_history_signal_text(listing),
        )
        results.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "candidate": candidate,
                "primary_listing": listing,
                "score": score,
                "score_components": components,
                "score_status": "heuristic_v1_not_calibrated",
                "reason_version": "decision_reason_v2",
                "strengths": positives,
                "product_advantages": product_advantages,
                "product_disadvantages": product_disadvantages,
                "market_risks": market_risks,
                "missing_data": missing_data,
                "development_suggestion": conclusion.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", ""),
                "conclusion": conclusion,
                "reason": decision_reason,
                "decision_reason": decision_reason,
                "saleable_window": saleable_window,
                "history_signals": list(listing.get("history_signals") or []),
            }
        )
    results.sort(
        key=lambda row: (
            -row["score"],
            _number(row["primary_listing"].get("new_release_rank")) or float("inf"),
            -(_number(row["primary_listing"].get("estimated_sales")) or 0),
            str(row.get("candidate_id") or ""),
        )
    )
    for position, row in enumerate(results, start=1):
        row["priority_rank"] = position
        row["screening_status"] = "SHORTLISTED" if position <= shortlist_limit else "REVIEW_LATER"
    return {
        "method": "new_product_discovery_score_v1",
        "score_status": "heuristic_not_calibrated_not_a_hard_gate",
        "weights": {
            "新品榜排名": 30,
            "预估月销量": 25,
            "上架新鲜度": 15,
            "Review竞争度": 10,
            "价格带适配": 10,
            "数据完整度": 10,
        },
        "counts": {
            "candidates": len(results),
            "shortlisted": min(shortlist_limit, len(results)),
            "review_later": max(0, len(results) - shortlist_limit),
        },
        "results": results,
    }


def table_rows(screening: dict) -> list[dict]:
    rows = []
    for scored in screening.get("results") or []:
        candidate = scored["candidate"]
        listing = scored["primary_listing"]
        marketplace = listing.get("marketplace")
        asin = listing.get("asin")
        domain = "amazon.de" if marketplace == "DE" else "amazon.com"
        product_url = listing.get("detail_url") or (f"https://www.{domain}/dp/{asin}" if asin else None)
        rows.append(
            {
                "站点": marketplace,
                "上架日期": listing.get("source_available_date") or listing.get("listing_date"),
                "Review数量": listing.get("review_count"),
                "售价（当地币种）": listing.get("price"),
                "大品类排名": listing.get("bsr"),
                "所在品类": _category_display_zh(listing.get("category_name") or listing.get("category_node")),
                "预估月销量": listing.get("estimated_sales"),
                "产品优点&特征": "；".join([_product_summary_zh(candidate), *scored["product_advantages"]]),
                "缺点": "；".join(scored["product_disadvantages"]),
                "生命周期": scored["saleable_window"],
                "ASIN": asin,
                "亚马逊产品链接": product_url,
                "图片": listing.get("image_url"),
                "得分": scored["score"],
                "结论": scored["conclusion"],
                "理由": scored["decision_reason"],
                "产品名称": candidate.get("product_name"),
                "评分明细": scored["score_components"],
            }
        )
    return rows
