"""Evidence-led screening for recent FBM products found by SellerSprite."""
from __future__ import annotations

from datetime import date, datetime
from statistics import median


SEASONAL_TERMS = (
    (("halloween", "万圣节"), "万圣节", {8, 9, 10}),
    (("christmas", "xmas", "圣诞"), "圣诞节", {10, 11, 12}),
    (("easter", "复活节"), "复活节", {2, 3, 4}),
    (("valentine", "情人节"), "情人节", {1, 2}),
    (("summer", "pool", "beach", "夏季"), "夏季", {5, 6, 7, 8}),
    (("back to school", "开学"), "开学季", {7, 8, 9}),
)


def _number(value):
    try:
        if value is None or isinstance(value, bool) or str(value).strip() == "":
            return None
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _age(value, as_of: date):
    try:
        listed = date.fromisoformat(str(value)[:10])
        days = (as_of - listed).days
        return days if days >= 0 else None
    except (ValueError, TypeError):
        return None


def _as_of(value):
    return date.fromisoformat(str(value)[:10]) if value else datetime.now().date()


def qualify_recent_fbm(records: list[dict], *, as_of_date=None, min_monthly_sales=100,
                       max_age_days=60) -> dict:
    """Require observed FBM, reliable listing date and enough estimated sales."""
    as_of = _as_of(as_of_date)
    accepted, rejected, seen = [], [], set()
    for row in records:
        site = str(row.get("marketplace") or "").upper()
        asin = str(row.get("asin") or "").upper()
        if not site or not asin or (site, asin) in seen:
            continue
        seen.add((site, asin))
        reasons = []
        age = _age(row.get("source_available_date") or row.get("listing_date"), as_of)
        sales = _number(row.get("estimated_sales"))
        if str(row.get("fulfillment") or "").upper() != "FBM":
            reasons.append("fulfillment_not_verified_fbm")
        if age is None or age > max_age_days:
            reasons.append("listing_not_verified_within_60_days")
        if sales is None or sales < min_monthly_sales:
            reasons.append("monthly_sales_below_threshold_or_missing")
        if reasons:
            rejected.append({"marketplace": site, "asin": asin, "reasons": reasons})
        else:
            accepted.append({**row, "marketplace": site, "asin": asin, "listing_age_days": age})
    return {
        "criteria": {"as_of_date": as_of.isoformat(), "max_age_days": max_age_days,
                     "fulfillment": "FBM", "min_monthly_sales": min_monthly_sales},
        "accepted": accepted, "rejected": rejected,
        "counts": {"examined": len(seen), "qualified": len(accepted), "rejected": len(rejected)},
    }


def _peer_median(row: dict, records: list[dict]):
    category = str(row.get("category_name") or "").strip().casefold()
    if not category:
        return None, 0
    prices = [
        _number(peer.get("price"))
        for peer in records
        if str(peer.get("marketplace") or "").upper() == row["marketplace"]
        and str(peer.get("category_name") or "").strip().casefold() == category
        and str(peer.get("currency") or "").upper() == str(row.get("currency") or "").upper()
    ]
    prices = [price for price in prices if price is not None and price > 0]
    return (median(prices), len(prices)) if len(prices) >= 3 else (None, len(prices))


def _cause_evidence(row: dict, all_records: list[dict], as_of: date) -> tuple[list[dict], str]:
    evidence = []
    price = _number(row.get("price"))
    peer_price, peers = _peer_median(row, all_records)
    if price is not None and peer_price and price <= peer_price * 0.85:
        evidence.append({"factor": "低价", "status": "observed",
                         "detail": f"售价{price:g}，同站同类目样本中位价{peer_price:g}（{peers}款）"})
    else:
        evidence.append({"factor": "低价", "status": "unverified",
                         "detail": f"同类可比价格不足或未显著低于中位价（可比{peers}款）"})
    title = str(row.get("product_name") or "").casefold()
    season = next(((name, months) for terms, name, months in SEASONAL_TERMS
                   if any(term in title for term in terms)), None)
    if season:
        name, months = season
        label = "当前在主题销售窗口" if as_of.month in months else "当前不在典型窗口"
        evidence.append({"factor": "季节性", "status": "hypothesis",
                         "detail": f"标题含{name}主题，{label}；需用历史销量趋势验证"})
        saleable = f"{min(months)}–{max(months)}月（{name}，需核验）"
    else:
        evidence.append({"factor": "季节性", "status": "unverified",
                         "detail": "未取得可验证的季节性销量趋势"})
        saleable = "全年可售（需核验季节性）"
    traffic = row.get("offsite_traffic_evidence")
    traffic_source = row.get("offsite_traffic_source")
    if traffic and traffic_source:
        evidence.append({"factor": "站外流量", "status": "reported",
                         "detail": f"{traffic}；来源：{traffic_source}，需核对归因"})
    else:
        evidence.append({"factor": "站外流量", "status": "unverified",
                         "detail": "未取得站外流量来源或归因数据"})
    innovation = row.get("innovation_evidence")
    innovation_source = row.get("innovation_source")
    if innovation and innovation_source:
        evidence.append({"factor": "功能创新", "status": "reported",
                         "detail": f"{innovation}；来源：{innovation_source}，需与同类功能比较"})
    else:
        evidence.append({"factor": "功能创新", "status": "unverified",
                         "detail": "标题或销量不能证明功能创新，需核对详情与竞品"})
    variants = _number(row.get("variation_count"))
    if variants is not None and variants >= 20:
        evidence.append({"factor": "超多变体", "status": "observed",
                         "detail": f"卖家精灵显示{int(variants)}个变体；对销量贡献待验证"})
    else:
        evidence.append({"factor": "超多变体", "status": "unverified",
                         "detail": f"变体数{int(variants)}" if variants is not None else "变体数缺失"})
    return evidence, saleable


def score_recent_fbm(qualified: list[dict], all_records: list[dict], *,
                     as_of_date=None, shortlist_limit=20) -> dict:
    as_of = _as_of(as_of_date)
    results = []
    for row in qualified:
        age = _age(row.get("source_available_date") or row.get("listing_date"), as_of)
        sales = _number(row.get("estimated_sales")) or 0
        growth = _number(row.get("sales_growth_percent"))
        reviews = _number(row.get("review_count"))
        price = _number(row.get("price"))
        variants = _number(row.get("variation_count"))
        peer_price, peer_count = _peer_median(row, all_records)
        components = {
            "月销量": 35 if sales >= 1000 else 29 if sales >= 500 else 23 if sales >= 200 else 16,
            "销量增长": 20 if growth is not None and growth >= 50 else 12 if growth is not None and growth >= 20 else 0,
            "上架时间": 15 if age is not None and age <= 30 else 10,
            "评论门槛": 10 if reviews is not None and reviews <= 30 else 7 if reviews is not None and reviews <= 100 else 3 if reviews is not None else 0,
            "相对价格": 10 if price is not None and peer_price and price <= peer_price * .85 else 5 if price is not None and peer_price else 0,
            "变体覆盖": 5 if variants is not None and variants >= 20 else 2 if variants is not None and variants >= 5 else 0,
            "证据完整度": sum(value is not None for value in (growth, reviews, price, variants, peer_price)),
        }
        score = sum(components.values())
        factors, saleable = _cause_evidence(row, all_records, as_of)
        cause_text = "；".join(
            f"{item['factor']}：{item['detail']}" for item in factors
        )
        growth_text = f"，近30天销量增长率{growth:g}%" if growth is not None else "，销量增长率未核实"
        conclusion = "🟢 优先调研" if score >= 70 else "🟡 继续核验"
        if growth is None and sales < 200:
            conclusion = "🟡 继续核验"
        reason = (
            f"热度证据：上架{age}天、FBM、预估月销量{sales:g}{growth_text}。"
            f"可能因素：{cause_text}。"
            f"判断：内部调研优先级{score}分；价格、季节或变体与销量的因果关系尚未证实。"
            f"下一步：核对流量来源、历史销量、竞品功能和实际履约方式。"
        )
        results.append({
            "candidate_id": f"{row['marketplace']}-{row['asin']}",
            "primary_listing": row,
            "score": score,
            "score_components": components,
            "conclusion": conclusion,
            "reason": reason,
            "hot_reason": cause_text,
            "factor_evidence": factors,
            "saleable_window": saleable,
            "peer_count": peer_count,
            "missing_data": [],
            "score_status": "j_evidence_priority_not_causal",
        })
    results.sort(key=lambda item: (-item["score"], -(_number(item["primary_listing"].get("estimated_sales")) or 0),
                                   item["candidate_id"]))
    for index, row in enumerate(results, 1):
        row["priority_rank"] = index
        row["screening_status"] = "SHORTLISTED" if index <= shortlist_limit else "REVIEW_LATER"
    return {
        "method": "recent_fbm_evidence_priority_v1",
        "score_status": "heuristic_not_calibrated_not_a_hard_gate",
        "counts": {"candidates": len(results), "shortlisted": min(shortlist_limit, len(results)),
                   "review_later": max(0, len(results) - shortlist_limit)},
        "results": results,
    }


def table_rows_recent_fbm(screening: dict) -> list[dict]:
    output = []
    for scored in screening["results"][:screening["counts"]["shortlisted"]]:
        row = scored["primary_listing"]
        site = row["marketplace"]
        asin = row["asin"]
        domain = "amazon.de" if site == "DE" else "amazon.com"
        output.append({
            "站点": site,
            "上架日期": row.get("source_available_date") or row.get("listing_date"),
            "Review数量": row.get("review_count"),
            "售价（当地币种）": row.get("price"),
            "大品类排名": row.get("bsr"),
            "所在品类": row.get("category_name"),
            "预估月销量": row.get("estimated_sales"),
            "产品优点&特征": "需核对详情和竞品，当前仅有商品标题与指标",
            "缺点": "需核对评论、样品和履约成本",
            "生命周期": scored["saleable_window"],
            "ASIN": asin,
            "亚马逊产品链接": row.get("detail_url") or f"https://www.{domain}/dp/{asin}",
            "图片": row.get("image_url"),
            "结论": scored["conclusion"],
            "理由": scored["reason"],
            "产品名称（原文）": row.get("product_name"),
            "FBM资格证据": f"上架{row['listing_age_days']}天；FBM；预估月销{_number(row.get('estimated_sales')):g}",
            "近期火爆原因": scored["hot_reason"],
            "得分": scored["score"],
        })
    return output
