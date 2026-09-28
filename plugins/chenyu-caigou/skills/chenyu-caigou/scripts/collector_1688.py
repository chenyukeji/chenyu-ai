"""Conservative 1688 supplier collection with human verification handoff.

This module intentionally does not solve or bypass CAPTCHAs. It uses one visible
Playwright persistent context, records a resumable checkpoint, and pauses when
1688 asks a human to log in or complete a security verification.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse, urlunsplit


class Collector1688Error(ValueError):
    pass


ALLOWED_HOST_SUFFIXES = ("1688.com",)
CHECKPOINT_VERSION = 1
MAX_QUERIES = 50
MAX_RESULTS_PER_QUERY = 30
MAX_DETAIL_PAGES = 5
DEFAULT_MANUAL_TIMEOUT_SECONDS = 300
DEFAULT_MIN_DELAY_SECONDS = 2.5
DEFAULT_MAX_DELAY_SECONDS = 5.5

CAPTCHA_SELECTORS = (
    "iframe[src*='captcha']",
    "iframe[src*='verify']",
    "[id*='nocaptcha']",
    "[class*='nc-container']",
    "[class*='baxia']",
    "[id*='baxia']",
    "[class*='punish']",
)
CAPTCHA_MARKERS = (
    "请完成验证",
    "滑动验证",
    "安全验证",
    "拖动下方滑块",
    "请按住滑块",
    "验证码",
    "访问过于频繁",
)
CAPTCHA_URL_MARKERS = ("captcha", "punish", "verify", "nocaptcha", "baxia")
LOGIN_URL_MARKERS = ("login.1688.com", "passport.1688.com")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def browser_status() -> dict:
    try:
        version = importlib.metadata.version("playwright")
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime:
            executable = Path(runtime.chromium.executable_path)
        return {
            "available": executable.exists(),
            "python_package": version,
            "chromium_executable": str(executable),
            "chromium_installed": executable.exists(),
        }
    except (importlib.metadata.PackageNotFoundError, ImportError) as exc:
        return {
            "available": False,
            "error": str(exc),
            "install": [
                "python -m pip install -r requirements-browser.txt",
                "python -m playwright install chromium",
            ],
        }


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise Collector1688Error(
            "Playwright is not installed; install requirements-browser.txt and run "
            "python -m playwright install chromium"
        ) from exc
    return sync_playwright


def validate_1688_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"}:
        raise Collector1688Error("1688 URL must use http or https")
    if parsed.username or parsed.password:
        raise Collector1688Error("credentials must not be embedded in a URL")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES):
        raise Collector1688Error(f"1688 collector does not allow host: {host}")
    return parsed.geturl()


def _redacted_observed_url(url: str) -> str:
    """Keep navigation evidence without persisting login or risk-control tokens."""
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def default_profile_dir() -> Path:
    configured = os.environ.get("CHENYU_BROWSER_DATA_DIR")
    base = Path(configured).expanduser() if configured else Path.cwd() / ".chenyu-browser-profiles"
    return (base / "1688").resolve()


def _launch_context(runtime, payload: dict):
    profile = Path(payload.get("profile_dir") or default_profile_dir()).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    width = max(1000, min(int(payload.get("viewport_width", 1440)), 2560))
    height = max(700, min(int(payload.get("viewport_height", 1000)), 1600))
    context = runtime.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=bool(payload.get("headless", False)),
        viewport={"width": width, "height": height},
        accept_downloads=False,
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(max(1000, min(int(payload.get("action_timeout_ms", 10000)), 30000)))
    page.set_default_navigation_timeout(
        max(10000, min(int(payload.get("navigation_timeout_ms", 90000)), 180000))
    )
    return context, page, profile


def _body_text(page, limit: int = 20000) -> str:
    try:
        return page.locator("body").inner_text(timeout=1500)[:limit]
    except Exception:
        return ""


def _selector_visible(page, selector: str) -> bool:
    try:
        return bool(page.locator(selector).first.is_visible(timeout=200))
    except Exception:
        return False


def detect_manual_gate(page) -> str | None:
    """Return a task-board state when 1688 requires human interaction."""
    current_url = str(getattr(page, "url", "") or "").lower()
    if any(marker in current_url for marker in LOGIN_URL_MARKERS):
        return "LOGIN_REQUIRED"
    if any(marker in current_url for marker in CAPTCHA_URL_MARKERS):
        return "CAPTCHA_DETECTED"
    if any(_selector_visible(page, selector) for selector in CAPTCHA_SELECTORS):
        return "CAPTCHA_DETECTED"
    text = _body_text(page).lower()
    if any(marker.lower() in text for marker in CAPTCHA_MARKERS):
        return "CAPTCHA_DETECTED"
    if _selector_visible(page, "input[type='password']") and any(
        marker in text for marker in ("登录", "账号登录", "密码登录")
    ):
        return "LOGIN_REQUIRED"
    return None


def _wait_for_manual_gate(page, timeout_seconds: int, poll_ms: int = 2000) -> str | None:
    """Wait for a person to clear a gate; return the uncleared state on timeout."""
    gate = detect_manual_gate(page)
    if not gate:
        return None
    deadline = time.monotonic() + max(0, min(int(timeout_seconds), 1800))
    while time.monotonic() < deadline:
        if page.is_closed():
            return gate
        page.wait_for_timeout(max(500, min(int(poll_ms), 5000)))
        gate = detect_manual_gate(page)
        if not gate:
            return None
    return gate


def _atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _safe_folder_component(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", str(value or "1688-sourcing"))
    text = re.sub(r"\s+", "-", text)
    return (text.strip(" .-_") or "1688-sourcing")[:50]


def _find_repository_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "plugins" / "chenyu-caigou").is_dir():
            return candidate
    raise Collector1688Error("cannot locate chenyu-ai; pass run_dir explicitly")


def _default_run_dir(first_query: str) -> Path:
    parent = _find_repository_root() / "outputs" / "chenyu-caigou" / "supplier-comparison"
    stem = f"{datetime.now().astimezone().date().isoformat()}_{_safe_folder_component(first_query)}"
    candidate = parent / stem
    if not candidate.exists():
        return candidate
    suffix = 2
    while (parent / f"{stem}_{suffix:02d}").exists():
        suffix += 1
    return parent / f"{stem}_{suffix:02d}"


def _normalize_queries(payload: dict) -> list[str]:
    raw = payload.get("queries")
    if raw is None:
        raw = [payload.get("query")]
    if not isinstance(raw, list):
        raise Collector1688Error("queries must be a list")
    queries = []
    for item in raw:
        value = re.sub(r"\s+", " ", str(item or "")).strip()
        if value and value not in queries:
            queries.append(value)
    if not queries:
        raise Collector1688Error("at least one non-empty 1688 query is required")
    if len(queries) > MAX_QUERIES:
        raise Collector1688Error(f"at most {MAX_QUERIES} queries per run")
    return queries


def _bounded_float(payload: dict, key: str, default: float, minimum: float, maximum: float) -> float:
    value = float(payload.get(key, default))
    return max(minimum, min(value, maximum))


def _new_config(payload: dict, queries: list[str], run_dir: Path) -> dict:
    minimum_delay = _bounded_float(
        payload, "min_delay_seconds", DEFAULT_MIN_DELAY_SECONDS, 1.0, 60.0
    )
    maximum_delay = _bounded_float(
        payload, "max_delay_seconds", DEFAULT_MAX_DELAY_SECONDS, minimum_delay, 120.0
    )
    return {
        "queries": queries,
        "run_dir": str(run_dir),
        "profile_dir": str(Path(payload.get("profile_dir") or default_profile_dir()).expanduser().resolve()),
        "headless": bool(payload.get("headless", False)),
        "max_results_per_query": max(
            1, min(int(payload.get("max_results_per_query", 20)), MAX_RESULTS_PER_QUERY)
        ),
        "detail_limit": max(0, min(int(payload.get("detail_limit", 5)), MAX_DETAIL_PAGES)),
        "manual_timeout_seconds": max(
            0,
            min(
                int(payload.get("manual_timeout_seconds", DEFAULT_MANUAL_TIMEOUT_SECONDS)),
                1800,
            ),
        ),
        "min_delay_seconds": minimum_delay,
        "max_delay_seconds": maximum_delay,
        "navigation_retries": max(0, min(int(payload.get("navigation_retries", 2)), 5)),
        "backoff_seconds": _bounded_float(payload, "backoff_seconds", 3.0, 1.0, 60.0),
        "action_timeout_ms": max(1000, min(int(payload.get("action_timeout_ms", 10000)), 30000)),
        "navigation_timeout_ms": max(
            10000, min(int(payload.get("navigation_timeout_ms", 90000)), 180000)
        ),
    }


def _new_checkpoint(config: dict) -> dict:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "state": "RUNNING",
        "message": "1688 supplier collection started",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "config": config,
        "cursor": {"query_index": 0, "phase": "search", "detail_index": 0},
        "current_url": None,
        "records_by_query": {},
        "errors": [],
    }


def _load_checkpoint(path: Path) -> dict:
    if not path.is_file():
        raise Collector1688Error(f"checkpoint does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("checkpoint_version") != CHECKPOINT_VERSION:
        raise Collector1688Error("unsupported or invalid 1688 checkpoint")
    return value


def _search_url(query: str) -> str:
    return f"https://s.1688.com/selloffer/offer_search.htm?keywords={quote_plus(query)}"


def _canonical_offer_url(value: str) -> tuple[str | None, str | None]:
    absolute = urljoin("https://www.1688.com/", str(value or "").strip())
    parsed = urlparse(absolute)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES):
        return None, None
    match = re.search(r"/offer/(\d+)\.html", parsed.path, re.I)
    if not match:
        return None, None
    offer_id = match.group(1)
    return f"https://detail.1688.com/offer/{offer_id}.html", offer_id


def _normalize_search_records(raw_records, query: str, limit: int) -> list[dict]:
    output = []
    seen = set()
    for raw in raw_records if isinstance(raw_records, list) else []:
        if not isinstance(raw, dict):
            continue
        product_url, offer_id = _canonical_offer_url(raw.get("product_url") or raw.get("href"))
        if not product_url or offer_id in seen:
            continue
        seen.add(offer_id)
        output.append(
            {
                "source": "1688",
                "source_keyword": query,
                "rank": len(output) + 1,
                "offer_id": offer_id,
                "product_name": str(raw.get("product_name") or raw.get("title") or "").strip() or None,
                "price": str(raw.get("price") or "").strip() or None,
                "moq": str(raw.get("moq") or "").strip() or None,
                "sales": str(raw.get("sales") or "").strip() or None,
                "supplier": str(raw.get("supplier") or "").strip() or None,
                "location": str(raw.get("location") or "").strip() or None,
                "product_url": product_url,
                "image_url": str(raw.get("image_url") or "").strip() or None,
                "detail_collected": False,
                "observed_at": _now_iso(),
            }
        )
        if len(output) >= limit:
            break
    return output


def _extract_search_records(page, query: str, limit: int) -> list[dict]:
    raw = page.evaluate(
        r"""limit => {
            const clean = value => (value || '').replace(/\s+/g, ' ').trim();
            const links = [...document.querySelectorAll('a[href*="/offer/"]')];
            const rows = [];
            const seen = new Set();
            for (const link of links) {
                const href = link.href || link.getAttribute('href') || '';
                const match = href.match(/\/offer\/(\d+)\.html/i);
                if (!match || seen.has(match[1])) continue;
                const card = link.closest('[class*="offer"], [class*="card"], [class*="item"], li') || link.parentElement;
                const text = clean(card ? card.innerText : link.innerText);
                const image = (card && card.querySelector('img')) || link.querySelector('img');
                const titleNode = (card && card.querySelector('[title]')) || link;
                const title = clean(titleNode.getAttribute && titleNode.getAttribute('title')) || clean(link.innerText) || clean(image && image.alt);
                const pick = patterns => {
                    for (const pattern of patterns) {
                        const found = text.match(pattern);
                        if (found) return clean(found[0]);
                    }
                    return '';
                };
                rows.push({
                    product_url: href,
                    product_name: title,
                    price: pick([/[¥￥]\s*\d+(?:\.\d+)?(?:\s*[-~]\s*[¥￥]?\s*\d+(?:\.\d+)?)?/]),
                    moq: pick([/\d+\s*(?:件|个|套|只|张|台|盒|包)起批/, /起批量?\s*[:：]?\s*\d+[^\s]*/]),
                    sales: pick([/(?:成交|已售|销量)\s*[:：]?\s*[\d万+]+[^\s]*/]),
                    supplier: clean(card && (card.querySelector('[class*="company"], [class*="shop"], [class*="supplier"]') || {}).innerText),
                    location: pick([/(?:广东|浙江|江苏|山东|福建|河北|河南|安徽|江西|湖南|湖北|四川|上海|北京|天津|重庆)[^\s]{0,10}/]),
                    image_url: image && (image.currentSrc || image.src || image.getAttribute('data-lazy-src') || image.getAttribute('data-src')) || ''
                });
                seen.add(match[1]);
                if (rows.length >= limit) break;
            }
            return rows;
        }""",
        limit,
    )
    return _normalize_search_records(raw, query, limit)


def _settle_search_page(page) -> None:
    """Give client-rendered result cards a bounded opportunity to appear."""
    try:
        page.locator("a[href*='/offer/']").first.wait_for(state="attached", timeout=8000)
    except Exception:
        pass


def _search_empty_confirmed(page) -> bool:
    text = _body_text(page, limit=12000)
    return any(marker in text for marker in ("未找到相关货源", "没有找到相关商品", "暂无相关产品"))


def _first_text(page, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            value = locator.get_attribute("content") if selector.startswith("meta[") else locator.inner_text()
            value = re.sub(r"\s+", " ", str(value or "")).strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _extract_detail(page) -> dict:
    text = _body_text(page, limit=30000)

    def match(pattern: str) -> str | None:
        found = re.search(pattern, text, re.I)
        return re.sub(r"\s+", " ", found.group(0)).strip() if found else None

    return {
        "product_name": _first_text(
            page,
            ("meta[property='og:title']", "h1", "[class*='title-text']", "[class*='offer-title']"),
        ),
        "price": match(r"[¥￥]\s*\d+(?:\.\d+)?(?:\s*[-~]\s*[¥￥]?\s*\d+(?:\.\d+)?)?"),
        "moq": match(r"(?:起批量?\s*[:：]?\s*)?\d+\s*(?:件|个|套|只|张|台|盒|包)起批"),
        "sales": match(r"(?:成交|已售|销量)\s*[:：]?\s*[\d万+]+[^\s]{0,6}"),
        "supplier": _first_text(
            page,
            ("[class*='company-name']", "[class*='factory-name']", "[class*='shop-name']"),
        ),
        "location": match(r"(?:所在地|发货地)\s*[:：]?\s*[^\s]{2,20}"),
        "detail_title": str(page.title() or "").strip() or None,
        "detail_collected": True,
        "detail_observed_at": _now_iso(),
    }


def _polite_delay(page, config: dict, rng: random.Random) -> None:
    seconds = rng.uniform(config["min_delay_seconds"], config["max_delay_seconds"])
    page.wait_for_timeout(int(seconds * 1000))


def _navigate_with_backoff(page, url: str, config: dict, rng: random.Random) -> None:
    target = validate_1688_url(url)
    attempts = config["navigation_retries"] + 1
    last_error = None
    for attempt in range(attempts):
        try:
            page.goto(target, wait_until="domcontentloaded")
            return
        except Exception as exc:  # Playwright raises several transport/navigation types.
            last_error = exc
            if attempt + 1 >= attempts:
                break
            delay = min(config["backoff_seconds"] * (2**attempt), 60.0)
            delay *= rng.uniform(0.85, 1.15)
            page.wait_for_timeout(int(delay * 1000))
    raise Collector1688Error(f"navigation failed after {attempts} attempt(s): {last_error}")


def _flatten_records(checkpoint: dict) -> list[dict]:
    records = []
    for query in checkpoint["config"]["queries"]:
        records.extend(checkpoint.get("records_by_query", {}).get(query, []))
    return records


def _result_from_checkpoint(checkpoint: dict, checkpoint_path: Path, results_path: Path) -> dict:
    state = checkpoint.get("state") or "PARTIAL"
    records = _flatten_records(checkpoint)
    if state == "COMPLETE":
        collection_status = "complete"
    elif state in {"CAPTCHA_DETECTED", "LOGIN_REQUIRED"}:
        collection_status = "blocked"
    else:
        collection_status = "partial"
    result = {
        "collection_status": collection_status,
        "task_state": state,
        "message": checkpoint.get("message"),
        "profile_dir": checkpoint["config"].get("profile_dir"),
        "checkpoint_path": str(checkpoint_path.resolve()),
        "results_path": str(results_path.resolve()),
        "resume_action": "resume_1688_suppliers" if collection_status != "complete" else None,
        "cursor": checkpoint.get("cursor"),
        "current_url": checkpoint.get("current_url"),
        "records": records,
        "errors": checkpoint.get("errors", []),
        "counts": {
            "queries_total": len(checkpoint["config"]["queries"]),
            "queries_completed": int(checkpoint.get("cursor", {}).get("query_index", 0)),
            "records": len(records),
            "details_collected": sum(bool(row.get("detail_collected")) for row in records),
        },
    }
    _atomic_write_json(results_path, result)
    return result


def _save_checkpoint(checkpoint_path: Path, checkpoint: dict, state: str, message: str) -> None:
    checkpoint["state"] = state
    checkpoint["message"] = message
    checkpoint["updated_at"] = _now_iso()
    _atomic_write_json(checkpoint_path, checkpoint)


def _manual_gate_ready(page, config: dict, checkpoint_path: Path, checkpoint: dict) -> bool:
    gate = detect_manual_gate(page)
    if not gate:
        return True
    message = (
        "1688 requires a human security verification; complete it in the visible browser"
        if gate == "CAPTCHA_DETECTED"
        else "1688 requires a human login; complete it in the visible browser"
    )
    checkpoint["current_url"] = _redacted_observed_url(getattr(page, "url", ""))
    _save_checkpoint(checkpoint_path, checkpoint, gate, message)
    if config["headless"] or config["manual_timeout_seconds"] <= 0:
        return False
    uncleared = _wait_for_manual_gate(page, config["manual_timeout_seconds"])
    if uncleared:
        _save_checkpoint(checkpoint_path, checkpoint, uncleared, message + "; timed out while waiting")
        return False
    _save_checkpoint(checkpoint_path, checkpoint, "RUNNING", "human verification completed; collection resumed")
    return True


def _resume_config(checkpoint: dict, payload: dict) -> dict:
    config = dict(checkpoint["config"])
    for key in (
        "headless",
        "manual_timeout_seconds",
        "min_delay_seconds",
        "max_delay_seconds",
        "navigation_retries",
        "backoff_seconds",
        "action_timeout_ms",
        "navigation_timeout_ms",
        "profile_dir",
    ):
        if key in payload:
            config[key] = payload[key]
    # Re-validate operational overrides while preserving the original query and limits.
    validated = _new_config({**config, "queries": config["queries"]}, config["queries"], Path(config["run_dir"]))
    validated["max_results_per_query"] = config["max_results_per_query"]
    validated["detail_limit"] = config["detail_limit"]
    return validated


def collect_1688_suppliers(payload: dict, *, resume: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise Collector1688Error("input must be a JSON object")
    if resume:
        run_dir_value = payload.get("run_dir")
        if not run_dir_value:
            raise Collector1688Error("run_dir is required to resume 1688 collection")
        run_dir = Path(run_dir_value).expanduser().resolve()
        checkpoint_path = run_dir / "1688-checkpoint.json"
        checkpoint = _load_checkpoint(checkpoint_path)
        checkpoint["config"] = _resume_config(checkpoint, payload)
        config = checkpoint["config"]
    else:
        queries = _normalize_queries(payload)
        run_dir = Path(payload.get("run_dir") or _default_run_dir(queries[0])).expanduser().resolve()
        checkpoint_path = run_dir / "1688-checkpoint.json"
        if checkpoint_path.exists():
            raise Collector1688Error(
                "run_dir already contains a checkpoint; use resume_1688_suppliers or choose a new run_dir"
            )
        config = _new_config(payload, queries, run_dir)
        checkpoint = _new_checkpoint(config)
    results_path = run_dir / "1688-results.json"
    run_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(checkpoint_path, checkpoint)
    if checkpoint.get("state") == "COMPLETE":
        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)

    rng = random.Random(payload.get("random_seed"))
    with _require_playwright()() as runtime:
        context, page, profile = _launch_context(runtime, config)
        config["profile_dir"] = str(profile)
        checkpoint["config"] = config
        try:
            _save_checkpoint(checkpoint_path, checkpoint, "RUNNING", "1688 supplier collection running")
            queries = config["queries"]
            while checkpoint["cursor"]["query_index"] < len(queries):
                query_index = checkpoint["cursor"]["query_index"]
                query = queries[query_index]
                if checkpoint["cursor"]["phase"] == "search":
                    search_url = _search_url(query)
                    checkpoint["current_url"] = search_url
                    try:
                        _navigate_with_backoff(page, search_url, config, rng)
                    except Collector1688Error as exc:
                        checkpoint["errors"].append(
                            {"query": query, "phase": "search", "error": str(exc), "observed_at": _now_iso()}
                        )
                        checkpoint["cursor"] = {
                            "query_index": query_index + 1,
                            "phase": "search",
                            "detail_index": 0,
                        }
                        _save_checkpoint(checkpoint_path, checkpoint, "RUNNING", "search failed; continuing")
                        continue
                    if not _manual_gate_ready(page, config, checkpoint_path, checkpoint):
                        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
                    _settle_search_page(page)
                    if not _manual_gate_ready(page, config, checkpoint_path, checkpoint):
                        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
                    records = _extract_search_records(page, query, config["max_results_per_query"])
                    if not _manual_gate_ready(page, config, checkpoint_path, checkpoint):
                        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
                    if not records and not _search_empty_confirmed(page):
                        checkpoint["errors"].append(
                            {
                                "query": query,
                                "phase": "search",
                                "error": "NO_RESULTS_EXTRACTED",
                                "observed_at": _now_iso(),
                            }
                        )
                    checkpoint["records_by_query"][query] = records
                    checkpoint["cursor"]["phase"] = "details"
                    checkpoint["cursor"]["detail_index"] = 0
                    _save_checkpoint(
                        checkpoint_path,
                        checkpoint,
                        "RUNNING",
                        f"search collected for {query}: {len(records)} record(s)",
                    )

                records = checkpoint["records_by_query"].get(query, [])
                detail_limit = min(config["detail_limit"], len(records))
                while checkpoint["cursor"]["detail_index"] < detail_limit:
                    detail_index = checkpoint["cursor"]["detail_index"]
                    row = records[detail_index]
                    checkpoint["current_url"] = row["product_url"]
                    _polite_delay(page, config, rng)
                    try:
                        _navigate_with_backoff(page, row["product_url"], config, rng)
                    except Collector1688Error as exc:
                        checkpoint["errors"].append(
                            {
                                "query": query,
                                "phase": "detail",
                                "offer_id": row.get("offer_id"),
                                "error": str(exc),
                                "observed_at": _now_iso(),
                            }
                        )
                        checkpoint["cursor"]["detail_index"] += 1
                        _save_checkpoint(checkpoint_path, checkpoint, "RUNNING", "detail failed; continuing")
                        continue
                    if not _manual_gate_ready(page, config, checkpoint_path, checkpoint):
                        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
                    detail = _extract_detail(page)
                    if not _manual_gate_ready(page, config, checkpoint_path, checkpoint):
                        return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
                    for key, value in detail.items():
                        if value not in (None, ""):
                            row[key] = value
                    checkpoint["cursor"]["detail_index"] += 1
                    _save_checkpoint(
                        checkpoint_path,
                        checkpoint,
                        "RUNNING",
                        f"detail {checkpoint['cursor']['detail_index']}/{detail_limit} collected for {query}",
                    )

                checkpoint["cursor"] = {
                    "query_index": query_index + 1,
                    "phase": "search",
                    "detail_index": 0,
                }
                if checkpoint["cursor"]["query_index"] < len(queries):
                    _polite_delay(page, config, rng)
                _save_checkpoint(
                    checkpoint_path,
                    checkpoint,
                    "RUNNING",
                    f"query completed: {query}",
                )

            final_state = "PARTIAL" if checkpoint["errors"] else "COMPLETE"
            _save_checkpoint(
                checkpoint_path,
                checkpoint,
                final_state,
                "1688 supplier collection completed" if final_state == "COMPLETE" else "collection completed with errors",
            )
            return _result_from_checkpoint(checkpoint, checkpoint_path, results_path)
        finally:
            context.close()
