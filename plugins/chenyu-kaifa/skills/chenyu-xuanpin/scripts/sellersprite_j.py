"""SellerSprite Product Research collector for the independent recent-FBM strategy."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from playwright_collector import (
    BrowserCollectionError, MAX_PAGES, _challenge_visible, _goto, _launch_context,
    _now_iso, _require_playwright, extract_sellersprite_table,
)

PRODUCT_RESEARCH_URL = "https://www.sellersprite.com/v3/product-research"
MARKET_LABELS = {"US": "美国站", "DE": "德国站"}


def _item(page, label: str):
    return page.locator(".item").filter(
        has=page.locator(".title", has_text=label)
    ).first


def collect_recent_fbm(payload: dict) -> dict:
    market = str(payload.get("marketplace") or "").upper()
    if market not in MARKET_LABELS:
        raise BrowserCollectionError("J 仅支持 US、DE 站点")
    min_sales = int(payload.get("min_monthly_sales", 100))
    max_pages = max(1, min(int(payload.get("max_pages", 3)), MAX_PAGES))
    keyword = str(payload.get("keyword") or "").strip()
    if min_sales < 1 or len(keyword) > 100:
        raise BrowserCollectionError("J 的销量阈值或关键词不合法")
    sync_playwright = _require_playwright()
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(
            runtime, {**payload, "source": "browser", "url": PRODUCT_RESEARCH_URL}
        )
        try:
            _goto(page, PRODUCT_RESEARCH_URL)
            if _challenge_visible(page):
                return {"collection_status": "blocked", "block_reason": "sellersprite_challenge",
                        "records": [], "profile_dir": str(profile)}
            market_button = page.get_by_text("选择站点", exact=True).locator("..").get_by_role(
                "button", name=MARKET_LABELS[market]
            )
            market_button.click()
            age_item = _item(page, "上架时间")
            age_item.locator("input").click()
            page.locator(".el-select-dropdown__item:visible").filter(has_text="近60天").click()
            fulfillment_item = _item(page, "配送方式")
            fulfillment_item.locator("label", has_text="FBM").click()
            sales_item = _item(page, "月销量")
            sales_item.locator("input[placeholder='最小值']").fill(str(min_sales))
            if keyword:
                _item(page, "包含关键词").locator("input").fill(keyword)
            if (age_item.locator("input").input_value() != "近60天"
                    or not fulfillment_item.locator("input[value='FBM']").is_checked()
                    or sales_item.locator("input[placeholder='最小值']").input_value() != str(min_sales)
                    or "active" not in (market_button.get_attribute("class") or "")):
                raise BrowserCollectionError("J 筛选条件未能在页面上确认")
            page.get_by_role("button", name="开始筛选").click()
            page.wait_for_function(
                "() => new URL(location.href).searchParams.get('sellerTypes')?.includes('FBM')",
                timeout=15000,
            )
            query = parse_qs(urlparse(page.url).query)
            if (query.get("putawayMonth") != ["2"]
                    or query.get("minSales") != [str(min_sales)]
                    or query.get("market") != [market]):
                raise BrowserCollectionError("J 查询参数与页面筛选条件不一致")
            records: list[dict] = []
            seen: set[str] = set()
            pages: list[dict] = []
            has_more = False
            for page_number in range(1, max_pages + 1):
                try:
                    page.wait_for_function(
                        "() => document.querySelectorAll('table tbody tr').length > 0 "
                        "|| document.body.innerText.includes('暂无数据')",
                        timeout=12000,
                    )
                except Exception:
                    pass
                found = extract_sellersprite_table(page, {"marketplace": market})
                for row in found:
                    asin = row.get("asin")
                    if asin and asin not in seen:
                        row["source_strategy"] = "J"
                        records.append(row)
                        seen.add(asin)
                pages.append({"page": page_number, "url": page.url, "records": len(found)})
                next_button = page.locator(".el-pagination .btn-next").first
                has_more = bool(next_button.count() and next_button.is_enabled())
                if not has_more or page_number == max_pages:
                    break
                previous = page.url
                next_button.click()
                page.wait_for_function("previous => location.href !== previous",
                                       arg=previous, timeout=12000)
            guest = "未登录" in page.locator("body").inner_text()[:1000]
            return {
                "collection_status": "partial" if guest or has_more else "complete",
                "records": records,
                "pages": pages,
                "source_metadata": {
                    "source": "sellersprite_product_research",
                    "marketplace": market,
                    "observed_at": _now_iso(),
                    "filters": {"listing_age_days": 60, "fulfillment": "FBM",
                                "min_monthly_sales": min_sales, "keyword": keyword or None},
                    "guest_view": guest,
                },
                "profile_dir": str(profile),
            }
        finally:
            context.close()
