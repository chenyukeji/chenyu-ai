"""Collect historical monthly sales surges through SellerSprite's visible filters."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from playwright_collector import (
    BrowserCollectionError, MAX_PAGES, _challenge_visible, _goto, _launch_context,
    _login_sellersprite_in_page, _require_playwright, _sellersprite_credentials,
    _wait_for_sellersprite_identity, extract_sellersprite_table,
)
from sellersprite_j import MARKET_LABELS, PRODUCT_RESEARCH_URL, _item


def _matches_month_query(response, market, month):
    parsed = urlparse(response.url)
    host = parsed.hostname or ""
    if not (host == "sellersprite.com" or host.endswith(".sellersprite.com")):
        return False
    if "/api/" not in parsed.path or "product" not in parsed.path:
        return False
    query = unquote(response.request.url) + " " + unquote(response.request.post_data or "")
    return bool(re.search(r"(?<![A-Za-z])" + market + r"(?![A-Za-z])", query)
                and (month in query or month.replace("-", "") in query))


def _query_month(page, trigger, market, month):
    # Confirm a successful response for this historical month before reading the table.
    with page.expect_response(lambda response: _matches_month_query(response, market, month), timeout=15000) as pending:
        trigger()
    response = pending.value
    if response.status != 200:
        raise BrowserCollectionError(f"historical_query_http_{response.status}")
    body = response.json()
    if not isinstance(body, dict) or body.get("code") != "OK" or body.get("success") is False:
        raise BrowserCollectionError("historical_query_failed")
    page.wait_for_function("() => !Array.from(document.querySelectorAll('.el-loading-mask')).some(e => e.offsetWidth || e.offsetHeight)", timeout=15000)
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def collect_monthly_surges(payload):
    market = str(payload.get("marketplace") or "").upper()
    months = payload.get("months") or []
    if market not in MARKET_LABELS or not months:
        raise BrowserCollectionError("历史季节性选品需要 US/DE 站点及历史月份")
    min_sales = int(payload.get("min_monthly_sales", 300))
    min_growth = float(payload.get("min_growth_percent", 10))
    if min_sales < 1 or min_growth < 0:
        raise BrowserCollectionError("历史销量和增长阈值不合法")
    max_pages = max(1, min(int(payload.get("max_pages", 3)), MAX_PAGES))
    username, password, _ = _sellersprite_credentials()
    records, coverage = [], []
    with _require_playwright()() as runtime:
        context, page, profile = _launch_context(runtime, {**payload, "url": PRODUCT_RESEARCH_URL})
        try:
            _goto(page, PRODUCT_RESEARCH_URL)
            if _challenge_visible(page):
                raise BrowserCollectionError("sellersprite_challenge")
            if _wait_for_sellersprite_identity(page) != "authenticated" and username and password:
                auth = _login_sellersprite_in_page(page, username, password, PRODUCT_RESEARCH_URL,
                                                  30, require_asin_query=False)
                if auth.get("login_status") != "verified":
                    raise BrowserCollectionError(auth.get("block_reason") or "sellersprite_login_unverified")
            if _wait_for_sellersprite_identity(page) != "authenticated":
                raise BrowserCollectionError("sellersprite_login_required")
            for month in months:
                _goto(page, PRODUCT_RESEARCH_URL)
                page.locator('.el-loading-mask.is-fullscreen').wait_for(state="hidden", timeout=15000)
                market_button = page.get_by_text("选择站点", exact=True).locator("..").get_by_role("button", name=MARKET_LABELS[market])
                market_button.click()
                month_button = page.locator('.choose-month button').filter(has_text=month).first
                if not month_button.count():
                    coverage.append({"month": month, "status": "unavailable", "reason": "历史月份不可访问"})
                    continue
                month_button.click()
                sales = _item(page, "月销量").locator("input[placeholder='最小值']")
                growth = _item(page, "月销量环比增长率").locator("input[placeholder='最小值']")
                sales.fill(str(min_sales))
                growth.fill(str(min_growth))
                if payload.get("keyword"):
                    _item(page, "包含关键词").locator("input").fill(str(payload["keyword"]))
                if ("active" not in (month_button.get_attribute("class") or "")
                        or "active" not in (market_button.get_attribute("class") or "")
                        or float(sales.input_value()) != min_sales or float(growth.input_value()) != min_growth):
                    raise BrowserCollectionError("历史月份或销量飙升筛选条件未能确认")
                _query_month(page, lambda: page.get_by_role("button", name="开始筛选").click(), market, month)
                seen, has_more = set(), False
                for page_number in range(1, max_pages + 1):
                    page.wait_for_function("() => document.querySelectorAll('table tbody tr').length > 0 || document.body.innerText.includes('暂无数据')", timeout=15000)
                    if _wait_for_sellersprite_identity(page) != "authenticated" or _challenge_visible(page):
                        raise BrowserCollectionError("sellersprite_session_lost")
                    for row in extract_sellersprite_table(page, {"marketplace": market}):
                        if row.get("asin") and row["asin"] not in seen:
                            row.update({"history_month": month, "source_strategy": "H",
                                        "source_type": "sellersprite_monthly_sales_surge"})
                            records.append(row)
                            seen.add(row["asin"])
                    next_button = page.locator('.el-pagination .btn-next').first
                    has_more = bool(next_button.count() and next_button.is_enabled())
                    if not has_more or page_number == max_pages:
                        break
                    _query_month(page, next_button.click, market, month)
                coverage.append({"month": month, "status": "partial" if has_more else "complete", "records": len(seen)})
            return {"collection_status": "complete" if all(x["status"] == "complete" for x in coverage) else "partial",
                    "records": records, "coverage": coverage, "marketplace": market, "profile_dir": str(profile)}
        except Exception as exc:
            reason = str(exc) if isinstance(exc, BrowserCollectionError) else type(exc).__name__
            return {"collection_status": "partial" if records else "blocked", "records": records,
                    "coverage": coverage, "block_reason": reason, "marketplace": market}
        finally:
            context.close()
