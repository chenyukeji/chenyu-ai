"""Collect real SellerSprite reverse-ASIN keywords for Listing research.

Credentials come only from the process environment. The output contains keyword
evidence, never account details or browser cookies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Also support importlib-based callers without an installed Python package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sellersprite_session import (launch_context, ensure_login, auth_state,
                                 assert_access, private_write, SessionError)

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
    result = ensure_login(page, username, password, BASE_URL)
    if result.get("login_status") != "verified":
        raise SessionError(result.get("block_reason") or "sellersprite_login_unverified")
    if not page.get_by_placeholder("请输入单个ASIN或产品链接").count():
        raise RuntimeError("SellerSprite reverse-ASIN form is unavailable")


def collect(page, market: str, asin: str) -> dict:
    assert_access(page)
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
    assert_access(page)
    page.get_by_role("button", name="立即查询").click()
    try:
        page.wait_for_url(lambda url: f"q={asin}" in url and
                          f"marketId={MARKET_IDS[market]}" in url, timeout=30000)
    except Exception as exc:
        assert_access(page)
        raise SessionError('sellersprite_query_timeout') from exc
    try:
        page.locator("table tbody tr td:nth-child(2) span.title[title]").first.wait_for(timeout=20000)
    except Exception:
        pass
    assert_access(page)
    if auth_state(page) != "authenticated":
        page.context._chenyu_sellersprite_store.failed('sellersprite_session_lost')
        raise SessionError("sellersprite_session_lost")
    rows = extract_rows(page)
    if not rows:
        # Empty DOM alone is not proof that SellerSprite has no keywords.
        raise SessionError('sellersprite_query_no_verified_rows')
    return {"marketplace": market, "asin": asin, "source_tool": "sellersprite_reverse_asin",
            "source_url": page.url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "period": page.locator("input:visible").nth(1).input_value(), "rows": rows}


def collect_requests(requests, output, open_runtime, username, password):
    results, failures = [], []
    pending = [{'marketplace': market, 'asin': asin, 'status': 'not_run'} for market, asin in requests]

    def checkpoint():
        private_write(output, {'queries': results, 'failures': failures, 'pending': pending})

    checkpoint()
    context = None
    try:
        with open_runtime() as runtime:
            try:
                context, page, _ = launch_context(runtime, {'headless': True})
                login(page, username, password)
                while pending:
                    item = pending[0]
                    try:
                        results.append(collect(page, item['marketplace'], item['asin']))
                    except Exception as exc:
                        reason = str(exc) if isinstance(exc, SessionError) else 'sellersprite_query_failed'
                        failures.append({**item, 'status': 'failed', 'reason': reason})
                        pending.pop(0)
                        checkpoint()
                        # Stop the batch on any unverified query; retain all not-run requests.
                        break
                    pending.pop(0)
                    checkpoint()
            finally:
                if context is not None:
                    context.close()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, SessionError) else 'sellersprite_collection_blocked'
        failures.append({'status': 'blocked', 'reason': reason})
    checkpoint()
    return results, failures


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
    results, failures = collect_requests(requests, args.out, sync_playwright, username, password)
    print(f"Collected {len(results)} SellerSprite ASIN queries; {len(failures)} failed; output: {args.out}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
