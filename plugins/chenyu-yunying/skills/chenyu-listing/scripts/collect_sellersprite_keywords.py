"""Collect real SellerSprite reverse-ASIN keywords for Listing research.

Credentials come only from the process environment. The output contains keyword
evidence, never account details or browser cookies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

MARKET_IDS = {"US": 1, "UK": 3, "DE": 4, "FR": 5, "IT": 35691, "ES": 44551}
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
BASE_URL = "https://www.sellersprite.com/v3/keyword-reverse/"


def parse_request(value: str) -> tuple[str, str]:
    try:
        market, asin = value.upper().split(":", 1)
    except ValueError as exc:
        raise ValueError("request must be MARKET:ASIN") from exc
    if market not in MARKET_IDS or not ASIN_RE.fullmatch(asin):
        raise ValueError(f"invalid market or ASIN in {value!r}")
    return market, asin


def extract_rows(page) -> list[dict]:
    rows = []
    seen = set()
    for table in page.locator("table").all():
        for row in table.locator("tbody tr").all():
            title = row.locator("td:nth-child(2) span.title[title]")
            if not title.count():
                continue
            keyword = (title.first.get_attribute("title") or "").strip()
            if not keyword or keyword.casefold() in seen:
                continue
            cells = row.locator("td")
            if cells.count() < 4:
                continue
            kinds = cells.nth(3).inner_text().strip().splitlines()
            seen.add(keyword.casefold())
            rows.append({
                "keyword": keyword,
                "traffic_types": [kind.strip() for kind in kinds if kind.strip()],
                "natural": "自然搜索词" in kinds,
            })
    return rows


def login(page, username: str, password: str) -> None:
    page.goto("https://www.sellersprite.com/cn/w/user/login", wait_until="domcontentloaded")
    account = page.locator("input[name='email']:visible").first
    secret = page.locator("input[type='password']:visible").first
    if account.count() and secret.count():
        account.fill(username)
        secret.fill(password)
        page.get_by_role("button", name=re.compile(r"立即登录|log\s*in|sign\s*in", re.I)).first.click()
        page.wait_for_url(lambda url: "/user/login" not in url and "/user/signin" not in url,
                          timeout=40000)
    page.goto(BASE_URL, wait_until="domcontentloaded")
    if page.locator("body").inner_text().find("立即登录") >= 0 and not page.get_by_placeholder(
            "请输入单个ASIN或产品链接").count():
        raise RuntimeError("SellerSprite login was not verified")
    if not page.get_by_placeholder("请输入单个ASIN或产品链接").count():
        raise RuntimeError("SellerSprite reverse-ASIN form is unavailable")


def collect(page, market: str, asin: str) -> dict:
    page.goto(f"{BASE_URL}?marketId={MARKET_IDS[market]}", wait_until="domcontentloaded")
    expected = {"US": "美国", "UK": "英国", "DE": "德国", "FR": "法国",
                "IT": "意大利", "ES": "西班牙"}[market]
    market_label = ""
    for _ in range(40):
        market_label = page.locator("input:visible").first.input_value()
        if expected in market_label:
            break
        page.wait_for_timeout(250)
    else:
        raise RuntimeError(f"SellerSprite market mismatch: expected {market}, got {market_label}")
    page.get_by_placeholder("请输入单个ASIN或产品链接").first.fill(asin)
    page.get_by_role("button", name="立即查询").click()
    try:
        page.wait_for_url(lambda url: f"q={asin}" in url and
                          f"marketId={MARKET_IDS[market]}" in url, timeout=30000)
    except Exception as exc:
        raise RuntimeError(f"SellerSprite {market}:{asin} query did not complete") from exc
    try:
        page.locator("table tbody tr td:nth-child(2) span.title[title]").first.wait_for(timeout=20000)
    except Exception:
        pass
    rows = extract_rows(page)
    if not rows:
        raise RuntimeError(f"SellerSprite returned no keyword rows for {market}:{asin}")
    return {"marketplace": market, "asin": asin, "source_tool": "sellersprite_reverse_asin",
            "source_url": page.url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "period": page.locator("input:visible").nth(1).input_value(), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", action="append", required=True, help="MARKET:ASIN; repeatable")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    requests = [parse_request(value) for value in args.request]
    username = os.environ.get("CHENYU_SELLERSPRITE_USERNAME", "").strip()
    password = os.environ.get("CHENYU_SELLERSPRITE_PASSWORD", "")
    if not username or not password:
        raise SystemExit("SellerSprite credentials are unavailable to this task")
    from playwright.sync_api import sync_playwright
    results = []
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            login(page, username, password)
            for market, asin in requests:
                try:
                    results.append(collect(page, market, asin))
                except Exception as exc:
                    failures.append({"marketplace": market, "asin": asin,
                                     "reason": str(exc).splitlines()[0][:240]})
            context.close()
        finally:
            browser.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"queries": results, "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collected {len(results)} SellerSprite ASIN queries; {len(failures)} failed; output: {args.out}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
