"""Visible-browser collectors for SellerSprite and Amazon pages.

The collector uses dedicated Playwright profiles. Credentials may be supplied
for one process after explicit authorization, but are never written to output.
"""
from __future__ import annotations

import importlib.metadata
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse


class BrowserCollectionError(ValueError):
    pass


ALLOWED_HOST_SUFFIXES = (
    "sellersprite.com",
    "amazon.com",
    "amazon.de",
    "amazon.fr",
    "amazon.it",
    "amazon.es",
)
MARKET_DISPLAY_PREFERENCES = {
    "US": {"currency": "USD", "locale": "en_US", "language_cookie": "lc-main"},
    "DE": {"currency": "EUR", "locale": "de_DE", "language_cookie": "lc-acbde"},
    "FR": {"currency": "EUR", "locale": "fr_FR", "language_cookie": "lc-acbfr"},
    "IT": {"currency": "EUR", "locale": "it_IT", "language_cookie": "lc-acbit"},
    "ES": {"currency": "EUR", "locale": "es_ES", "language_cookie": "lc-acbes"},
}
SUPPORTED_EXTRACTORS = {"amazon_search", "amazon_product", "amazon_ranked_list", "sellersprite_table"}
MAX_PAGES = 20
MAX_ACTIONS = 100
MAX_RECORDS = 5000
MAX_ASIN_ENRICHMENT = 100
DEFAULT_SELLERSPRITE_QUERY_TIMEOUT_MS = 8000
DEFAULT_SELLERSPRITE_QUERY_DELAY_MS = 200
DEFAULT_SELLERSPRITE_QUERY_POLL_MS = 200
DEFAULT_SELLERSPRITE_EMPTY_GRACE_MS = 800
DEFAULT_SELLERSPRITE_BATCH_SIZE = 60
ASIN_PATTERN = re.compile(r"(?<![A-Z0-9])B[A-Z0-9]{9}(?![A-Z0-9])", re.I)
ASIN_VALUE_PATTERN = re.compile(r"^[A-Z0-9]{10}$", re.I)
DEFAULT_SELLERSPRITE_CREDENTIALS = Path(__file__).resolve().parents[5] / ".chenyu-secrets" / "sellersprite.json"
SELLERSPRITE_COMPETITOR_HEADERS = (
    "选择",
    "#",
    "内容标记",
    "产品信息",
    "大类BSR",
    "销量趋势",
    "销量(父) 增长率",
    "销售额",
    "子体销量 子体销售额",
    "变体数",
    "价格 Q&A",
    "评分数 月新增",
    "评分 留评率",
    "FBA 毛利率",
    "上架时间",
    "配送 买家运费",
    "操作",
)

HEADER_ALIASES = {
    "marketplace": ("站点", "市场", "marketplace", "market", "site"),
    "asin": ("asin",),
    "parent_asin": ("父asin", "父体asin", "parent asin", "parent_asin"),
    "product_name": ("商品名称", "产品名称", "商品标题", "产品信息", "标题", "product", "title"),
    "seller_location": ("卖家所在地", "卖家国家", "卖家地区", "seller location", "seller country"),
    "fulfillment": ("配送方式", "配送", "履约方式", "fulfillment", "shipping"),
    "price": ("价格", "售价", "price"),
    "currency": ("币种", "currency"),
    "bsr": ("大类bsr", "bsr", "best sellers rank"),
    "estimated_sales": ("销量父", "月销量", "近30天销量", "预估销量", "estimated sales", "monthly sales", "units sold"),
    "estimated_revenue": ("销售额", "预估销售额", "revenue"),
    "child_estimated_sales": ("子体销量", "variation sold", "child sales"),
    "child_estimated_revenue": ("子体销售额", "variation revenue", "child revenue"),
    "variation_count": ("变体数", "variations count", "variations"),
    "sales_period": ("销量周期", "统计周期", "sales period"),
    "review_count": ("评论数", "评价数", "评分数", "rating count", "review count", "reviews", "ratings"),
    "rating": ("评分", "星级", "rating", "star rating"),
    "monthly_rating_increase": ("月新增", "rating increase", "monthly new ratings"),
    "fba_fee": ("fba费用", "fba fee", "fba"),
    "gross_margin": ("毛利率", "gross margin"),
    "delivery_price": ("买家运费", "delivery price"),
    "source_available_date": ("上架日期", "上架时间", "发布日期", "available date", "launch date"),
    "product_advantages": ("产品优点", "产品卖点", "核心卖点", "advantages", "selling points"),
    "product_disadvantages": ("产品缺点", "产品不足", "disadvantages", "weaknesses"),
    "review_pain_points": ("评论痛点", "差评痛点", "review pain points", "complaints"),
    "saleable_window": ("可售时间", "可售月份", "销售月份", "saleable window", "selling months"),
    "peak_months": ("旺季月份", "旺季", "peak months", "peak season"),
    "seasonality": ("季节性", "seasonality"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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
        raise BrowserCollectionError(
            "Playwright is not installed; install requirements-browser.txt and run "
            "python -m playwright install chromium"
        ) from exc
    return sync_playwright


def validate_url(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"}:
        raise BrowserCollectionError("browser URL must use http or https")
    if parsed.username or parsed.password:
        raise BrowserCollectionError("credentials must not be embedded in browser URLs")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES):
        raise BrowserCollectionError(f"browser host is not allowed: {host}")
    return parsed.geturl()


def _safe_profile_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "default")).strip("-").lower()
    return name[:64] or "default"


def default_profile_dir(source: str) -> Path:
    configured = os.environ.get("CHENYU_BROWSER_DATA_DIR")
    base = Path(configured).expanduser() if configured else Path.cwd() / ".chenyu-browser-profiles"
    return base.resolve() / _safe_profile_name(source)


def _sellersprite_credentials(payload: dict) -> tuple[str, str, str | None]:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if username and password:
        return username, password, "process_input"
    configured = payload.get("credentials_path") or os.environ.get("CHENYU_SELLERSPRITE_CREDENTIALS")
    path = Path(configured).expanduser().resolve() if configured else DEFAULT_SELLERSPRITE_CREDENTIALS
    if not path.exists():
        return username, password, None
    try:
        saved = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserCollectionError(f"SellerSprite credentials file is invalid: {path}") from exc
    username = username or str(saved.get("username") or "").strip()
    password = password or str(saved.get("password") or "")
    return username, password, "local_credentials_file"


def _display_preferences(payload: dict) -> dict:
    market = str(payload.get("marketplace") or "").upper()
    defaults = MARKET_DISPLAY_PREFERENCES.get(market, {})
    currency = str(payload.get("display_currency") or defaults.get("currency") or "").upper() or None
    locale = str(payload.get("display_locale") or defaults.get("locale") or "") or None
    if currency and currency not in {"USD", "EUR", "GBP"}:
        raise BrowserCollectionError("display_currency must be USD, EUR, or GBP")
    return {
        "currency": currency,
        "locale": locale,
        "language_cookie": defaults.get("language_cookie"),
    }


def _apply_display_preferences(context, payload: dict) -> dict:
    preferences = _display_preferences(payload)
    parsed = urlparse(validate_url(payload.get("url")))
    host = (parsed.hostname or "").lower()
    if "amazon." not in host:
        return preferences
    cookie_url = f"https://{host}"
    cookies = []
    if preferences["currency"]:
        cookies.append({"name": "i18n-prefs", "value": preferences["currency"], "url": cookie_url})
    if preferences["locale"] and preferences["language_cookie"]:
        cookies.append(
            {
                "name": preferences["language_cookie"],
                "value": preferences["locale"],
                "url": cookie_url,
            }
        )
    if cookies:
        context.add_cookies(cookies)
    return preferences


def _launch_context(runtime, payload: dict):
    source = str(payload.get("source") or "browser")
    profile = Path(payload.get("profile_dir") or default_profile_dir(source)).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    headless = bool(payload.get("headless", False))
    width = int(payload.get("viewport_width", 1440))
    height = int(payload.get("viewport_height", 1000))
    context = runtime.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=headless,
        viewport={"width": max(800, min(width, 2560)), "height": max(600, min(height, 1600))},
        accept_downloads=False,
    )
    _apply_display_preferences(context, payload)
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(int(payload.get("action_timeout_ms", 10000)))
    page.set_default_navigation_timeout(int(payload.get("navigation_timeout_ms", 90000)))
    return context, page, profile


def _goto(page, url: str) -> None:
    page.goto(validate_url(url), wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass


def _challenge_visible(page) -> bool:
    selectors = (
        "input[name='captcha']",
        "input#captchacharacters",
        "img[src*='captcha']",
        "iframe[src*='captcha']",
    )
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=200):
                return True
        except Exception:
            continue
    try:
        text = page.locator("body").inner_text(timeout=1000).lower()[:10000]
    except Exception:
        return False
    markers = ("robot check", "enter the characters you see below", "验证码", "人机验证")
    return any(marker in text for marker in markers)


def _wait_for_challenge_clearance(page, timeout_seconds: int) -> bool:
    if not _challenge_visible(page):
        return True
    deadline = time.monotonic() + max(0, min(timeout_seconds, 900))
    while time.monotonic() < deadline:
        if page.is_closed():
            return False
        if not _challenge_visible(page):
            return True
        page.wait_for_timeout(500)
    return False


def _locator_value(locator, mode: str, attribute: str | None = None):
    if mode == "value":
        return locator.input_value()
    if mode == "attribute":
        if not attribute:
            raise BrowserCollectionError("attribute readback requires attribute name")
        return locator.get_attribute(attribute)
    return locator.inner_text()


def _read_filter_values(page, specs) -> dict:
    if not specs:
        return {}
    if not isinstance(specs, dict):
        raise BrowserCollectionError("filter_readbacks must be an object")
    output = {}
    for name, spec in specs.items():
        if isinstance(spec, str):
            spec = {"selector": spec, "mode": "text"}
        if not isinstance(spec, dict) or not spec.get("selector"):
            raise BrowserCollectionError(f"invalid filter readback: {name}")
        locator = page.locator(spec["selector"]).first
        try:
            value = _locator_value(locator, spec.get("mode", "text"), spec.get("attribute"))
            output[str(name)] = value.strip() if isinstance(value, str) else value
        except Exception:
            output[str(name)] = None
    return output


def _ranked_list_identity(url: str) -> dict:
    match = re.search(r"/gp/new-releases/[^/?]+/(\d+)(?:[/?]|$)", url, re.I)
    return {
        "ranking_type": "new_releases" if "/gp/new-releases/" in url.lower() else None,
        "category_node": match.group(1) if match else None,
    }


def _expand_ranked_list(page) -> int:
    stable_at_bottom = 0
    previous_count = -1
    for _ in range(45):
        current_count = page.locator("#gridItemRoot").count()
        state = page.evaluate(
            """() => ({
                atBottom: window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 200,
                step: Math.max(Math.floor(window.innerHeight * 0.8), 600)
            })"""
        )
        if state["atBottom"] and current_count == previous_count:
            stable_at_bottom += 1
            if stable_at_bottom >= 8:
                return current_count
        else:
            stable_at_bottom = 0
        previous_count = current_count
        page.evaluate("step => window.scrollBy(0, step)", state["step"])
        page.wait_for_timeout(400)
    return page.locator("#gridItemRoot").count()


def _rank_integrity(records: list[dict]) -> dict:
    ranks = [int(item["new_release_rank"]) for item in records if item.get("new_release_rank") is not None]
    if not ranks:
        return {"missing_ranks": [], "duplicate_ranks": []}
    unique = set(ranks)
    missing = [rank for rank in range(min(unique), max(unique) + 1) if rank not in unique]
    duplicates = sorted({rank for rank in unique if ranks.count(rank) > 1})
    return {"missing_ranks": missing, "duplicate_ranks": duplicates}


def _run_actions(page, actions) -> None:
    actions = actions or []
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise BrowserCollectionError(f"interactions must be a list with at most {MAX_ACTIONS} actions")
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            raise BrowserCollectionError(f"interaction {index} must be an object")
        kind = action.get("type")
        selector = action.get("selector")
        if kind == "wait":
            page.wait_for_timeout(max(0, min(int(action.get("milliseconds", 500)), 10000)))
            continue
        if not selector:
            raise BrowserCollectionError(f"interaction {index} requires selector")
        locator = page.locator(selector).first
        if kind == "click":
            locator.click()
        elif kind == "fill":
            input_type = (locator.get_attribute("type") or "").lower()
            if input_type == "password" or "password" in selector.lower():
                raise BrowserCollectionError("password fields must be completed manually in the visible browser")
            locator.fill(str(action.get("value", "")))
        elif kind == "select_option":
            locator.select_option(str(action.get("value", "")))
        elif kind == "press":
            locator.press(str(action.get("key") or "Enter"))
        elif kind == "check":
            locator.check()
        elif kind == "uncheck":
            locator.uncheck()
        elif kind == "wait_for":
            locator.wait_for(state=action.get("state", "visible"))
        else:
            raise BrowserCollectionError(f"unsupported interaction type: {kind}")
        settle_ms = max(0, min(int(action.get("settle_ms", 500)), 10000))
        if settle_ms:
            page.wait_for_timeout(settle_ms)


def _first_text(root, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        try:
            locator = root.locator(selector).first
            if locator.count():
                value = locator.inner_text(timeout=1000).strip()
                if value:
                    return value
        except Exception:
            continue
    return None


def _first_attribute(root, selectors: tuple[str, ...], attribute: str) -> str | None:
    for selector in selectors:
        try:
            locator = root.locator(selector).first
            if locator.count():
                value = locator.get_attribute(attribute, timeout=1000)
                if value:
                    return value
        except Exception:
            continue
    return None


def _parse_decimal(value: str | None):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"[-+]?\d[\d\s.,]*", value.replace("\u00a0", " "))
    if not match:
        return None
    suffix_text = value[match.end() :].lstrip().upper()
    multiplier = 1
    if suffix_text.startswith("K"):
        multiplier = 1_000
    elif suffix_text.startswith("M"):
        multiplier = 1_000_000
    elif suffix_text.startswith("B"):
        multiplier = 1_000_000_000
    number = re.sub(r"\s+", "", match.group(0))
    if "," in number and "." in number:
        decimal = "," if number.rfind(",") > number.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        number = number.replace(thousands, "").replace(decimal, ".")
    elif "," in number:
        tail = number.rsplit(",", 1)[-1]
        number = number.replace(",", ".") if len(tail) in {1, 2} else number.replace(",", "")
    elif number.count(".") > 1:
        number = number.replace(".", "")
    try:
        return float(number) * multiplier
    except ValueError:
        return None


def _parse_integer(value: str | None):
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


def _currency_from_text(value: str | None, marketplace: str | None):
    text = (value or "").upper()
    if "USD" in text or "$" in text:
        return "USD"
    if "EUR" in text or "€" in text:
        return "EUR"
    if "GBP" in text or "£" in text:
        return "GBP"
    if str(marketplace).upper() == "US":
        return "USD"
    if str(marketplace).upper() in {"DE", "FR", "IT", "ES"}:
        return "EUR"
    return None


def extract_amazon_search(page, payload: dict) -> list[dict]:
    records = []
    marketplace = str(payload.get("marketplace") or "").upper() or None
    observed_at = _now_iso()
    rows = page.locator("[data-component-type='s-search-result'][data-asin]")
    for index in range(min(rows.count(), MAX_RECORDS)):
        row = rows.nth(index)
        asin = (row.get_attribute("data-asin") or "").strip().upper()
        if not asin:
            continue
        title = _first_text(row, ("h2", "h2 span", "[data-cy='title-recipe']"))
        href = _first_attribute(row, ("h2 a", "a.a-link-normal[href*='/dp/']"), "href")
        price_text = _first_text(row, (".a-price .a-offscreen", ".a-price-whole"))
        review_text = _first_text(row, ("[data-csa-c-slot-id='alf-reviews']", "span.a-size-base.s-underline-text"))
        image_url = _first_attribute(row, ("img.s-image", "img[data-image-latency]", "img[src]"), "src")
        body_text = _first_text(row, (":scope",)) or ""
        prime_eligible = "prime" in body_text.lower()
        if not prime_eligible:
            try:
                prime_eligible = bool(
                    row.locator("i.a-icon-prime, [aria-label*='Prime'], [data-csa-c-content-id*='prime']").count()
                )
            except Exception:
                pass
        records.append(
            {
                "marketplace": marketplace,
                "asin": asin,
                "product_name": title,
                "price": _parse_decimal(price_text),
                "currency": _currency_from_text(price_text, marketplace),
                "review_count": _parse_integer(review_text),
                # Prime eligibility alone does not identify the seller's
                # fulfillment model. Keep fulfillment unknown until a product
                # page or source table exposes the dispatching party.
                "fulfillment": None,
                "prime_eligible": prime_eligible,
                "observed_at": observed_at,
                "source_ref": page.url.rstrip("/") + f"#asin={asin}",
                "source_entity_id": asin,
                "sponsored": "sponsored" in body_text.lower() or "gesponsert" in body_text.lower(),
                "detail_url": urljoin(page.url, href) if href else None,
                "image_url": image_url,
            }
        )
    return records


def extract_amazon_ranked_list(page, payload: dict) -> list[dict]:
    records = []
    marketplace = str(payload.get("marketplace") or "").upper() or None
    observed_at = _now_iso()
    rows = page.locator("#gridItemRoot")
    for index in range(min(rows.count(), MAX_RECORDS)):
        row = rows.nth(index)
        asin = (_first_attribute(row, ("[data-asin]",), "data-asin") or "").strip().upper()
        if not asin:
            continue
        rank_text = _first_text(row, (".zg-bdg-text",))
        title = _first_text(
            row,
            (
                "[class*='p13n-sc-css-line-clamp']",
                ".p13n-sc-truncate-desktop-type2",
                ".zg-grid-general-faceout a[href*='/dp/'][role='link']",
            ),
        )
        if not title:
            title = _first_attribute(row, ("img.p13n-product-image", "img[alt]"), "alt")
        href = _first_attribute(
            row,
            (".zg-grid-general-faceout a[href*='/dp/'][role='link']", "a[href*='/dp/']"),
            "href",
        )
        price_text = _first_text(row, (".p13n-sc-price", "[class*='p13n-sc-price_']", ".a-color-price"))
        review_text = _first_text(row, ("a[href*='/product-reviews/'] span.a-size-small",))
        rating_text = _first_text(row, ("a[href*='/product-reviews/'] .a-icon-alt", ".a-icon-alt"))
        image_url = _first_attribute(row, ("img.p13n-product-image", "img[src]"), "src")
        rank = _parse_integer(rank_text) or index + 1
        records.append(
            {
                "marketplace": marketplace,
                "asin": asin,
                "product_name": title,
                "new_release_rank": rank,
                "price": _parse_decimal(price_text),
                "currency": _currency_from_text(price_text, marketplace),
                "review_count": _parse_integer(review_text),
                "rating": _parse_decimal(rating_text),
                "fulfillment": None,
                "observed_at": observed_at,
                "source_ref": page.url.rstrip("/") + f"#rank={rank}",
                "source_entity_id": asin,
                "detail_url": urljoin(page.url, href) if href else None,
                "image_url": image_url,
                "ranking_type": "new_releases",
            }
        )
    return records


def _asin_from_url(url: str) -> str | None:
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", url, re.I)
    return match.group(1).upper() if match else None


def extract_amazon_product(page, payload: dict) -> list[dict]:
    marketplace = str(payload.get("marketplace") or "").upper() or None
    asin = _asin_from_url(page.url)
    try:
        asin = (page.locator("input#ASIN").get_attribute("value") or asin or "").upper() or None
    except Exception:
        pass
    title = _first_text(page, ("#productTitle", "h1"))
    image_selectors = ("#landingImage", "#imgTagWrapperId img", "#main-image-container img")
    image_url = _first_attribute(page, image_selectors, "data-old-hires") or _first_attribute(
        page, image_selectors, "src"
    )
    price_text = _first_text(
        page,
        ("#corePrice_feature_div .a-price .a-offscreen", "#priceblock_ourprice", ".a-price .a-offscreen"),
    )
    review_text = _first_text(page, ("#acrCustomerReviewText", "[data-hook='total-review-count']"))
    seller = _first_text(page, ("#sellerProfileTriggerId", "#merchant-info"))
    shipper = _first_text(page, ("#tabular-buybox", "#merchant-info", "#shipsFromSoldBy_feature_div"))
    fulfillment = None
    shipper_lower = (shipper or "").lower()
    if "amazon" in shipper_lower:
        fulfillment = "FBA"
    elif shipper:
        fulfillment = "FBM"
    bullets = []
    try:
        for item in page.locator("#feature-bullets li span.a-list-item").all_inner_texts():
            value = item.strip()
            if value:
                bullets.append(value)
    except Exception:
        pass
    return [
        {
            "marketplace": marketplace,
            "asin": asin,
            "product_name": title,
            "price": _parse_decimal(price_text),
            "currency": _currency_from_text(price_text, marketplace),
            "review_count": _parse_integer(review_text),
            "seller_name": seller,
            "fulfillment": fulfillment,
            "fulfillment_raw": shipper,
            "feature_bullets": bullets,
            "image_url": image_url,
            "observed_at": _now_iso(),
            "source_ref": page.url,
            "source_entity_id": asin or page.url,
        }
    ]


def _normalise_header(value: str) -> str:
    return re.sub(r"[\s_:/()（）-]+", "", str(value or "")).lower()


def _canonical_header(header: str, custom_aliases: dict | None = None) -> str | None:
    aliases = dict(HEADER_ALIASES)
    if custom_aliases:
        for key, values in custom_aliases.items():
            aliases[str(key)] = tuple(values if isinstance(values, list) else [values])
    normalized = _normalise_header(header)
    special_cases = (
        (("子体销量", "variationsold"), "child_estimated_sales"),
        (("销量父", "unitssoldgrowth"), "estimated_sales"),
        (("评分数", "ratingcount"), "review_count"),
        (("评分留评率", "ratingratingsrate"), "rating"),
        (("配送买家运费", "fulfillmentdeliveryprice"), "fulfillment"),
        (("fba毛利率", "fbagrossmargin"), "fba_fee"),
    )
    for needles, canonical in special_cases:
        if any(needle in normalized for needle in needles):
            return canonical
    for canonical, values in aliases.items():
        for alias in values:
            alias_normalized = _normalise_header(alias)
            if normalized == alias_normalized or (alias_normalized and alias_normalized in normalized):
                return canonical
    return None


def _normalise_date(value: str | None):
    if not value:
        return None
    text = value.strip()
    match = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](20\d{2})", text)
    if match:
        return f"{int(match.group(3)):04d}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"
    return text


def _normalise_fulfillment(value: str | None):
    text = (value or "").strip().upper()
    if "FBA" in text:
        return "FBA"
    if "FBM" in text or "自发货" in (value or ""):
        return "FBM"
    if "AMZ" in text or "AMAZON" in text:
        return "AMZ"
    return text or None


def _cell_lines(value: str | None) -> list[str]:
    return [line.strip() for line in re.split(r"[\r\n]+", value or "") if line.strip()]


def _extract_asin(*values) -> str | None:
    for value in values:
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            text = str(candidate or "")
            match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", text, re.I)
            if match:
                return match.group(1).upper()
            match = re.search(r"\bASIN\s*[:：]\s*([A-Z0-9]{10})\b", text, re.I)
            if match:
                return match.group(1).upper()
            match = ASIN_PATTERN.search(text)
            if match:
                return match.group(0).upper()
    return None


def _parse_percent(value: str | None):
    match = re.search(r"[-+]?\d[\d.,]*\s*%", value or "")
    return _parse_decimal(match.group(0)) if match else None


def _parse_sellersprite_combined_fields(record: dict, headers: list[str], cells: list[str], links: list[str]) -> None:
    record["asin"] = record.get("asin") or _extract_asin(cells, links)
    for index, header in enumerate(headers):
        if index >= len(cells):
            continue
        normalized = _normalise_header(header)
        value = cells[index]
        lines = _cell_lines(value)
        if not lines:
            continue
        if "产品信息" in normalized or normalized in {"product", "productinfo"}:
            record["asin"] = record.get("asin") or _extract_asin(value, links)
            parent_match = re.search(r"父\s*ASIN\s*[:：]\s*(B[A-Z0-9]{9})", value, re.I)
            if parent_match:
                record["parent_asin"] = parent_match.group(1).upper()
            brand_match = re.search(r"品牌\s*[:：]\s*([^\r\n]+)", value, re.I)
            if brand_match:
                record["brand"] = html.unescape(brand_match.group(1).strip())
            if not record.get("product_name") or "\n" in str(record.get("product_name")):
                title_candidates = [line for line in lines if not _extract_asin(line) and len(line) > 8]
                if title_candidates:
                    record["product_name"] = html.unescape(title_candidates[0])
        elif "大类bsr" in normalized or normalized == "bsr":
            record["bsr"] = _parse_integer(lines[0])
            if len(lines) > 1:
                category_candidates = [
                    line
                    for line in lines[1:]
                    if re.search(r"[A-Za-z\u4e00-\u9fff]", line) and "%" not in line
                ]
                if category_candidates:
                    record["category_name"] = category_candidates[0]
        elif "销量父" in normalized or "unitssoldgrowth" in normalized:
            record["estimated_sales"] = _parse_decimal(lines[0])
            record["sales_growth_percent"] = _parse_percent(value)
        elif "子体销量" in normalized or "variationsold" in normalized:
            record["child_estimated_sales"] = _parse_decimal(lines[0])
            if len(lines) > 1:
                record["child_estimated_revenue"] = _parse_decimal(lines[1])
        elif "销售额" in normalized or normalized == "revenue":
            record["estimated_revenue"] = _parse_decimal(lines[0])
        elif "价格" in normalized or normalized.startswith("price"):
            record["price"] = _parse_decimal(lines[0])
        elif "评分数" in normalized or "ratingcount" in normalized:
            record["review_count"] = _parse_integer(lines[0])
            if record["review_count"] is None and lines[0] in {"-", "—", "–"}:
                record["review_count"] = 0
            if len(lines) > 1:
                record["monthly_rating_increase"] = _parse_integer(lines[1])
        elif "评分留评率" in normalized or "ratingratingsrate" in normalized:
            record["rating"] = _parse_decimal(lines[0])
            record["rating_rate_percent"] = _parse_percent(value)
        elif "fba毛利率" in normalized or "fbagrossmargin" in normalized:
            record["fba_fee"] = _parse_decimal(lines[0])
            record["gross_margin_percent"] = _parse_percent(value)
        elif "配送买家运费" in normalized or "fulfillmentdeliveryprice" in normalized:
            record["fulfillment"] = _normalise_fulfillment(lines[0])
            if len(lines) > 1:
                record["delivery_price"] = _parse_decimal(lines[1])


def _extract_best_table(page, table_selector: str | None = None) -> dict:
    script = """
    ({selector}) => {
      const roots = selector
        ? Array.from(document.querySelectorAll(selector))
        : Array.from(document.querySelectorAll('table, [role="grid"]'));
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const candidates = roots.filter(visible).map((root, tableIndex) => {
        let headers = Array.from(root.querySelectorAll('thead th, [role="columnheader"]'))
          .filter(visible).map(el => (el.innerText || el.textContent || '').trim());
        let rowEls = Array.from(root.querySelectorAll('tbody tr'));
        if (!rowEls.length) {
          rowEls = Array.from(root.querySelectorAll('[role="row"]')).filter(row => !row.querySelector('[role="columnheader"]'));
        }
        const rows = rowEls.filter(visible).map(row => {
          const cells = Array.from(row.querySelectorAll('td, [role="gridcell"]'))
            .filter(visible).map(el => (el.innerText || el.textContent || '').trim());
          const links = Array.from(row.querySelectorAll('a[href]')).map(a => a.href);
          const imageUrls = Array.from(row.querySelectorAll('img[src]')).map(img => img.currentSrc || img.src).filter(Boolean);
          return {cells, links, imageUrls};
        }).filter(row => row.cells.some(Boolean));
        if (!headers.length && rows.length) headers = rows[0].cells.map((_, i) => `column_${i + 1}`);
        return {tableIndex, headers, rows, score: headers.length * 10 + rows.length};
      });
      candidates.sort((a, b) => b.score - a.score);
      return candidates[0] || {tableIndex: null, headers: [], rows: [], score: 0};
    }
    """
    return page.evaluate(script, {"selector": table_selector})


def _usable_sellersprite_image_url(value) -> bool:
    url = str(value or "").strip()
    if not url:
        return False
    lowered = url.lower()
    return not (
        "sellersprite.com/v3/webapp/static/" in lowered
        or lowered.endswith("/ai-guide.png")
    )


def extract_sellersprite_table(page, payload: dict) -> list[dict]:
    table = _extract_best_table(page, payload.get("table_selector"))
    headers = table.get("headers") or []
    if len(headers) == len(SELLERSPRITE_COMPETITOR_HEADERS) and all(
        re.fullmatch(r"column_\d+", header or "", re.I) for header in headers
    ):
        headers = list(SELLERSPRITE_COMPETITOR_HEADERS)
    canonical = [_canonical_header(header, payload.get("header_aliases")) for header in headers]
    observed_at = _now_iso()
    marketplace = str(payload.get("marketplace") or "").upper() or None
    output = []
    for index, raw in enumerate(table.get("rows") or [], start=1):
        cells = raw.get("cells") or []
        if len(headers) == len(SELLERSPRITE_COMPETITOR_HEADERS) and len(cells) < 8:
            if output and cells:
                detail_text = cells[0]
                detail_asin = _extract_asin(detail_text)
                if detail_asin and output[-1].get("asin") == detail_asin:
                    output[-1]["detail_text"] = detail_text
                    seller_match = re.search(r"BuyBox\s*卖家\s*[:：]\s*([^\r\n(]+)", detail_text, re.I)
                    if seller_match:
                        output[-1]["seller_name"] = seller_match.group(1).strip()
            continue
        record = {"raw_cells": {headers[i]: cells[i] for i in range(min(len(headers), len(cells)))}}
        for i, field in enumerate(canonical):
            if field and i < len(cells) and cells[i].strip():
                record[field] = cells[i].strip()
        _parse_sellersprite_combined_fields(record, headers, cells, raw.get("links") or [])
        image_url = next(
            (value for value in (raw.get("imageUrls") or []) if _usable_sellersprite_image_url(value)),
            None,
        )
        if image_url:
            record["image_url"] = image_url
        amazon_links = [link for link in (raw.get("links") or []) if "amazon." in link.lower() and "/dp/" in link.lower()]
        if amazon_links:
            record["detail_url"] = amazon_links[0]
        record["marketplace"] = str(record.get("marketplace") or marketplace or "").upper() or None
        record["asin"] = str(record.get("asin") or "").strip().upper() or None
        record["parent_asin"] = str(record.get("parent_asin") or "").strip().upper() or None
        record["price"] = _parse_decimal(record.get("price"))
        record["estimated_sales"] = _parse_decimal(record.get("estimated_sales"))
        record["estimated_revenue"] = _parse_decimal(record.get("estimated_revenue"))
        record["child_estimated_sales"] = _parse_decimal(record.get("child_estimated_sales"))
        record["child_estimated_revenue"] = _parse_decimal(record.get("child_estimated_revenue"))
        record["variation_count"] = _parse_integer(record.get("variation_count"))
        record["review_count"] = _parse_integer(record.get("review_count"))
        record["rating"] = _parse_decimal(record.get("rating"))
        record["monthly_rating_increase"] = _parse_integer(record.get("monthly_rating_increase"))
        record["bsr"] = _parse_integer(record.get("bsr"))
        record["fba_fee"] = _parse_decimal(record.get("fba_fee"))
        record["delivery_price"] = _parse_decimal(record.get("delivery_price"))
        record["currency"] = str(record.get("currency") or _currency_from_text(None, marketplace) or "").upper() or None
        seller_location = str(record.get("seller_location") or "").strip().upper()
        record["seller_location"] = "CN" if seller_location in {"CN", "中国", "CHINA"} else seller_location or None
        record["fulfillment"] = _normalise_fulfillment(record.get("fulfillment"))
        record["source_available_date"] = _normalise_date(record.get("source_available_date"))
        record["observed_at"] = observed_at
        record["source_ref"] = page.url.rstrip("/") + f"#table={table.get('tableIndex')}&row={index}"
        record["source_entity_id"] = record.get("asin") or (raw.get("links") or [None])[0] or record["source_ref"]
        output.append(record)
    return output[:MAX_RECORDS]


def _sellersprite_login_block_reason(page, asin_input) -> str | None:
    try:
        if asin_input.count() and not asin_input.is_disabled():
            return None
    except Exception:
        pass
    try:
        body = page.locator("body").inner_text(timeout=1500).lower()[:12000]
    except Exception:
        body = ""
    if any(marker in body for marker in ("未登录", "登录", "sign in", "log in")):
        return "sellersprite_login_required"
    return "sellersprite_asin_query_unavailable"


def _wait_for_sellersprite_asin_input(page, timeout_ms: int = 12000):
    deadline = time.monotonic() + max(0, min(timeout_ms, 30000)) / 1000
    locator = page.locator("input[placeholder*='ASIN' i]:visible").first
    while time.monotonic() < deadline:
        try:
            if locator.count() and not locator.is_disabled():
                return locator
        except Exception:
            pass
        page.wait_for_timeout(250)
        locator = page.locator("input[placeholder*='ASIN' i]:visible").first
    return locator


def _select_sellersprite_market(page, marketplace: str) -> str:
    option_names = {
        "US": ("美国站", "United States"),
        "DE": ("德国站", "Germany"),
    }
    names = option_names.get(marketplace)
    if not names:
        raise BrowserCollectionError("SellerSprite ASIN enrichment currently supports US and DE")
    selectors = page.locator("input.el-input__inner[readonly]:visible")
    if not selectors.count():
        raise BrowserCollectionError("SellerSprite marketplace selector was not found")
    values_seen = []
    for index in range(min(selectors.count(), 20)):
        selector = selectors.nth(index)
        try:
            current = selector.input_value().strip()
            values_seen.append(current)
            if any(name.lower() in current.lower() for name in names):
                return current
            selector.click()
            page.wait_for_timeout(250)
            for name in names:
                option = page.locator(".el-select-dropdown__item:visible").filter(has_text=name).first
                if option.count():
                    option.click()
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        selected = selector.input_value().strip()
                        if any(expected.lower() in selected.lower() for expected in names):
                            return selected
                        page.wait_for_timeout(200)
                    values_seen.append(f"{current} -> {selector.input_value().strip()}")
                    break
            page.keyboard.press("Escape")
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
    raise BrowserCollectionError(
        f"SellerSprite marketplace option was not found: {marketplace}; controls={values_seen}"
    )


def _sellersprite_query_is_busy(page, search_button) -> bool:
    try:
        if search_button.is_disabled():
            return True
    except Exception:
        pass
    for selector in (".el-loading-mask:visible", ".el-icon-loading:visible", "[aria-busy='true']:visible"):
        try:
            if page.locator(selector).count():
                return True
        except Exception:
            continue
    return False


def _sellersprite_result_is_explicitly_empty(page) -> bool:
    """Return true only when the visible competitor table reports an empty result."""
    try:
        return bool(
            page.evaluate(
                """
                () => {
                  const visible = (element) => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' &&
                      rect.width > 0 && rect.height > 0;
                  };
                  const emptyPattern = /(暂无数据|暂无结果|无数据|未查询到|没有找到|no data|no results?|not found)/i;
                  return [...document.querySelectorAll('.el-table')].some((table) => {
                    if (!visible(table) || !/(产品信息|product)/i.test(table.innerText || '')) return false;
                    const empty = table.querySelector('.el-table__empty-text, .el-empty__description');
                    return Boolean(empty && visible(empty) && emptyPattern.test(empty.innerText || ''));
                  });
                }
                """
            )
        )
    except Exception:
        return False


def _sellersprite_batch_url(url: str, marketplace: str, asins: list[str], batch_size: int) -> str:
    """Build the UI URL used by SellerSprite for a multi-ASIN lookup."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "market": marketplace,
            "asins": json.dumps(asins, ensure_ascii=True, separators=(",", ":")),
            "page": "1",
            "size": str(max(len(asins), min(batch_size, DEFAULT_SELLERSPRITE_BATCH_SIZE))),
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def _query_sellersprite_batch(
    page,
    payload: dict,
    marketplace: str,
    asins: list[str],
    query_timeout_ms: int,
    query_poll_ms: int,
    empty_grace_ms: int,
) -> tuple[list[dict], int, str]:
    """Run one UI batch lookup and return every requested ASIN visible in the table."""
    started = time.monotonic()
    target_asins = set(asins)
    batch_url = _sellersprite_batch_url(page.url, marketplace, asins, len(asins))
    _goto(page, batch_url)
    deadline = started + query_timeout_ms / 1000
    matched_by_asin = {}
    last_change = started
    stop_reason = "timeout"
    while time.monotonic() < deadline:
        if _challenge_visible(page):
            stop_reason = "login_or_challenge"
            break
        page_records = extract_sellersprite_table(page, {**payload, "marketplace": marketplace})
        current = {
            str(record.get("asin") or "").upper(): record
            for record in page_records
            if str(record.get("asin") or "").upper() in target_asins
        }
        if len(current) != len(matched_by_asin):
            matched_by_asin = current
            last_change = time.monotonic()
        if len(matched_by_asin) == len(target_asins):
            stop_reason = "batch_matched"
            break
        elapsed_ms = int((time.monotonic() - started) * 1000)
        stable_ms = int((time.monotonic() - last_change) * 1000)
        if elapsed_ms >= empty_grace_ms and _sellersprite_result_is_explicitly_empty(page):
            stop_reason = "batch_explicit_empty"
            break
        if matched_by_asin and elapsed_ms >= empty_grace_ms and stable_ms >= empty_grace_ms:
            stop_reason = "batch_partial"
            break
        page.wait_for_timeout(query_poll_ms)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return list(matched_by_asin.values()), elapsed_ms, stop_reason


def collect_sellersprite_by_asin(payload: dict) -> dict:
    url = validate_url(payload.get("url") or "https://www.sellersprite.com/v3/competitor-lookup")
    marketplace = str(payload.get("marketplace") or "").upper()
    if marketplace not in {"US", "DE"}:
        raise BrowserCollectionError("marketplace must be US or DE for SellerSprite ASIN enrichment")
    requested_asins = payload.get("asins") or []
    if not isinstance(requested_asins, list):
        raise BrowserCollectionError("asins must be a list")
    asins = []
    for value in requested_asins:
        asin = str(value or "").strip().upper()
        if not ASIN_VALUE_PATTERN.fullmatch(asin):
            raise BrowserCollectionError(f"invalid ASIN: {value}")
        if asin not in asins:
            asins.append(asin)
    if not asins:
        raise BrowserCollectionError("at least one ASIN is required")
    if len(asins) > MAX_ASIN_ENRICHMENT:
        raise BrowserCollectionError(f"at most {MAX_ASIN_ENRICHMENT} ASINs may be enriched per run")

    sync_playwright = _require_playwright()
    records = []
    outcomes = []
    errors = []
    query_timeout_ms = max(
        1000,
        min(int(payload.get("query_timeout_ms", DEFAULT_SELLERSPRITE_QUERY_TIMEOUT_MS)), 60000),
    )
    query_delay_ms = max(
        0,
        min(int(payload.get("query_delay_ms", DEFAULT_SELLERSPRITE_QUERY_DELAY_MS)), 5000),
    )
    query_poll_ms = max(
        100,
        min(int(payload.get("query_poll_ms", DEFAULT_SELLERSPRITE_QUERY_POLL_MS)), 1000),
    )
    empty_grace_ms = max(
        300,
        min(int(payload.get("empty_grace_ms", DEFAULT_SELLERSPRITE_EMPTY_GRACE_MS)), 5000),
    )
    batch_queries = bool(payload.get("batch_queries", True))
    batch_size = max(
        1,
        min(int(payload.get("batch_size", DEFAULT_SELLERSPRITE_BATCH_SIZE)), DEFAULT_SELLERSPRITE_BATCH_SIZE),
    )
    username, password, credential_source = _sellersprite_credentials(payload)
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(runtime, {**payload, "url": url})
        try:
            _goto(page, url)
            if _challenge_visible(page):
                cleared = False
                if not payload.get("headless", False):
                    cleared = _wait_for_challenge_clearance(page, int(payload.get("manual_timeout_seconds", 120)))
                if not cleared:
                    return {
                        "collection_status": "blocked",
                        "block_reason": "login_or_challenge_requires_user",
                        "records": [],
                        "outcomes": [],
                        "profile_dir": str(profile),
                        "counts": {"requested": len(asins), "enriched": 0, "missing": len(asins)},
                    }
            asin_input = _wait_for_sellersprite_asin_input(page, 5000)
            block_reason = _sellersprite_login_block_reason(page, asin_input)
            auth_result = None
            if block_reason and username and password:
                auth_result = _login_sellersprite_in_page(
                    page,
                    username,
                    password,
                    url,
                    int(payload.get("manual_timeout_seconds", 180)),
                )
                asin_input = _wait_for_sellersprite_asin_input(page, 12000)
                block_reason = _sellersprite_login_block_reason(page, asin_input)
            if block_reason:
                return {
                    "collection_status": "blocked",
                    "block_reason": block_reason,
                    "auth_result": auth_result,
                    "records": [],
                    "outcomes": [{"asin": asin, "status": "blocked"} for asin in asins],
                    "profile_dir": str(profile),
                    "source_metadata": {
                        "source": payload.get("source") or "sellersprite_competitor_lookup",
                        "marketplace": marketplace,
                        "selected_market": None,
                        "url": page.url,
                        "observed_at": _now_iso(),
                        "credential_source": credential_source,
                    },
                    "counts": {"requested": len(asins), "enriched": 0, "missing": len(asins)},
                }
            selected_market = _select_sellersprite_market(page, marketplace)
            search_button = page.get_by_role("button", name=re.compile(r"立即查询|search", re.I)).first
            if not search_button.count():
                raise BrowserCollectionError("SellerSprite ASIN search button was not found")

            pending_asins = list(asins)
            if batch_queries and len(asins) > 1:
                pending_asins = []
                for offset in range(0, len(asins), batch_size):
                    batch_asins = asins[offset : offset + batch_size]
                    batch_records, batch_elapsed_ms, batch_stop_reason = _query_sellersprite_batch(
                        page,
                        payload,
                        marketplace,
                        batch_asins,
                        query_timeout_ms,
                        query_poll_ms,
                        empty_grace_ms,
                    )
                    batch_record_by_asin = {
                        str(record.get("asin") or "").upper(): record for record in batch_records
                    }
                    for asin in batch_asins:
                        record = batch_record_by_asin.get(asin)
                        if record:
                            record["enrichment_source"] = "sellersprite_competitor_lookup"
                            record["requested_asin"] = asin
                            records.append(record)
                            outcomes.append(
                                {
                                    "asin": asin,
                                    "status": "enriched",
                                    "record_count": 1,
                                    "elapsed_ms": batch_elapsed_ms,
                                    "stop_reason": batch_stop_reason,
                                    "query_mode": "batch",
                                }
                            )
                        else:
                            pending_asins.append(asin)
                    if batch_stop_reason == "login_or_challenge":
                        errors.extend(
                            {"asin": asin, "code": "LOGIN_OR_CHALLENGE"} for asin in pending_asins
                        )
                        outcomes.extend(
                            {
                                "asin": asin,
                                "status": "blocked",
                                "record_count": 0,
                                "elapsed_ms": batch_elapsed_ms,
                                "stop_reason": batch_stop_reason,
                                "query_mode": "batch",
                            }
                            for asin in pending_asins
                        )
                        pending_asins = []
                        break
                    if query_delay_ms and offset + batch_size < len(asins):
                        page.wait_for_timeout(query_delay_ms)
                asin_input = _wait_for_sellersprite_asin_input(page, 5000)
                search_button = page.get_by_role("button", name=re.compile(r"立即查询|search", re.I)).first

            for asin in pending_asins:
                asin_input.fill(asin)
                search_button.click()
                query_started = time.monotonic()
                deadline = query_started + query_timeout_ms / 1000
                matched = []
                stop_reason = "timeout"
                saw_busy = _sellersprite_query_is_busy(page, search_button)
                while time.monotonic() < deadline:
                    if _challenge_visible(page):
                        errors.append({"asin": asin, "code": "LOGIN_OR_CHALLENGE"})
                        stop_reason = "login_or_challenge"
                        break
                    page_records = extract_sellersprite_table(page, {**payload, "marketplace": marketplace})
                    matched = [record for record in page_records if record.get("asin") == asin]
                    if matched:
                        stop_reason = "matched"
                        break
                    elapsed_ms = int((time.monotonic() - query_started) * 1000)
                    is_busy = _sellersprite_query_is_busy(page, search_button)
                    if is_busy:
                        saw_busy = True
                    if elapsed_ms >= 300 and saw_busy and not is_busy:
                        page.wait_for_timeout(250)
                        page_records = extract_sellersprite_table(
                            page, {**payload, "marketplace": marketplace}
                        )
                        matched = [record for record in page_records if record.get("asin") == asin]
                        stop_reason = "matched" if matched else "query_completed_without_match"
                        break
                    if (
                        elapsed_ms >= empty_grace_ms
                        and not is_busy
                        and _sellersprite_result_is_explicitly_empty(page)
                    ):
                        stop_reason = "explicit_empty"
                        break
                    page.wait_for_timeout(query_poll_ms)
                elapsed_ms = int((time.monotonic() - query_started) * 1000)
                if matched:
                    for record in matched:
                        record["enrichment_source"] = "sellersprite_competitor_lookup"
                        record["requested_asin"] = asin
                    records.extend(matched)
                    outcomes.append(
                        {
                            "asin": asin,
                            "status": "enriched",
                            "record_count": len(matched),
                            "elapsed_ms": elapsed_ms,
                            "stop_reason": stop_reason,
                            "query_mode": "single_fallback" if batch_queries and len(asins) > 1 else "single",
                        }
                    )
                else:
                    outcomes.append(
                        {
                            "asin": asin,
                            "status": "not_found_or_unavailable",
                            "record_count": 0,
                            "elapsed_ms": elapsed_ms,
                            "stop_reason": stop_reason,
                            "query_mode": "single_fallback" if batch_queries and len(asins) > 1 else "single",
                        }
                    )
                if query_delay_ms:
                    page.wait_for_timeout(query_delay_ms)

            enriched_asins = {record.get("asin") for record in records}
            status = "complete" if len(enriched_asins) == len(asins) and not errors else "partial"
            result = {
                "collection_status": status,
                "records": records,
                "outcomes": outcomes,
                "errors": errors,
                "profile_dir": str(profile),
                "source_metadata": {
                    "source": payload.get("source") or "sellersprite_competitor_lookup",
                    "marketplace": marketplace,
                    "selected_market": selected_market,
                    "url": page.url,
                    "observed_at": _now_iso(),
                    "credential_source": credential_source,
                    "query_timeout_ms": query_timeout_ms,
                    "query_delay_ms": query_delay_ms,
                    "query_poll_ms": query_poll_ms,
                    "batch_queries": batch_queries,
                    "batch_size": batch_size,
                },
                "counts": {
                    "requested": len(asins),
                    "enriched": len(enriched_asins),
                    "missing": len(asins) - len(enriched_asins),
                },
            }
            output_path = payload.get("output_path")
            if output_path:
                target = Path(output_path).expanduser().resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(target)
                result["output_path"] = str(target)
            return result
        finally:
            context.close()


def _extract_records(page, payload: dict) -> list[dict]:
    extractor = payload.get("extractor")
    if extractor == "amazon_search":
        return extract_amazon_search(page, payload)
    if extractor == "amazon_product":
        return extract_amazon_product(page, payload)
    if extractor == "amazon_ranked_list":
        return extract_amazon_ranked_list(page, payload)
    if extractor == "sellersprite_table":
        return extract_sellersprite_table(page, payload)
    raise BrowserCollectionError(f"unsupported extractor: {extractor}")


def _next_selector(payload: dict) -> str | None:
    if payload.get("next_selector"):
        return str(payload["next_selector"])
    if payload.get("extractor") == "amazon_search":
        return "a.s-pagination-next:not(.s-pagination-disabled)"
    if payload.get("extractor") == "amazon_ranked_list":
        return "li.a-last a, a:has-text('Next page'), a:has-text('Nächste Seite')"
    if payload.get("extractor") == "sellersprite_table":
        return ".ant-pagination-next:not(.ant-pagination-disabled) button, .el-pagination .btn-next:not([disabled])"
    return None


def _click_next(page, selector: str | None, previous_fingerprint: str) -> bool:
    if not selector:
        return False
    locator = page.locator(selector).first
    try:
        if not locator.count() or not locator.is_visible() or locator.is_disabled():
            return False
        locator.click()
        page.wait_for_timeout(700)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        current = page.url + "|" + (page.locator("body").inner_text(timeout=3000)[:1000])
        return current != previous_fingerprint
    except Exception:
        return False


def _next_available(page, selector: str | None) -> bool:
    if not selector:
        return False
    locator = page.locator(selector).first
    try:
        return bool(locator.count() and locator.is_visible() and not locator.is_disabled())
    except Exception:
        return False


def _filter_verification(requested: dict | None, applied: dict) -> str:
    if not isinstance(requested, dict) or not applied:
        return "unverified"
    if any(value is None for value in applied.values()):
        return "partial"
    requested_text = {str(k): str(v).strip().lower() for k, v in requested.items()}
    applied_text = {str(k): str(v).strip().lower() for k, v in applied.items()}
    return "verified" if requested_text == applied_text else "mismatch"


def login(payload: dict) -> dict:
    url = validate_url(payload.get("url"))
    selector = payload.get("success_selector")
    url_pattern = payload.get("success_url_regex")
    if not selector and not url_pattern:
        raise BrowserCollectionError("browser_login requires success_selector or success_url_regex")
    timeout_seconds = max(1, min(int(payload.get("manual_timeout_seconds", 300)), 900))
    sync_playwright = _require_playwright()
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(runtime, payload)
        try:
            _goto(page, url)
            deadline = time.monotonic() + timeout_seconds
            success = False
            while time.monotonic() < deadline and not page.is_closed():
                selector_ok = False
                url_ok = False
                if selector:
                    try:
                        selector_ok = page.locator(selector).first.is_visible(timeout=200)
                    except Exception:
                        pass
                if url_pattern:
                    url_ok = re.search(str(url_pattern), page.url) is not None
                if selector_ok or url_ok:
                    success = True
                    break
                page.wait_for_timeout(500)
            return {
                "login_status": "verified" if success else "timeout",
                "current_url": page.url,
                "title": page.title(),
                "profile_dir": str(profile),
            }
        finally:
            context.close()


def _login_sellersprite_in_page(page, username: str, password: str, destination: str, timeout_seconds: int) -> dict:
    login_url = "https://www.sellersprite.com/cn/w/user/login"
    _goto(page, login_url)
    page.wait_for_timeout(800)
    account_input = page.locator("input[name='email']:visible").first
    password_input = page.locator("input[type='password']:visible").first
    submit = page.get_by_role("button", name=re.compile(r"立即登录|log\s*in|sign\s*in", re.I)).first
    if not account_input.count() or not password_input.count() or not submit.count():
        _goto(page, destination)
        asin_input = _wait_for_sellersprite_asin_input(page, 12000)
        if asin_input.count() and not asin_input.is_disabled():
            return {"login_status": "verified", "current_url": page.url}
        raise BrowserCollectionError(f"SellerSprite password-login form was not found at {page.url}")
    account_input.fill(username)
    password_input.fill(password)
    submit.click()

    deadline = time.monotonic() + max(5, min(timeout_seconds, 900))
    challenge_seen = False
    while time.monotonic() < deadline and not page.is_closed():
        try:
            body = page.locator("body").inner_text(timeout=1000)
        except Exception:
            body = ""
        challenge_seen = challenge_seen or any(
            marker in body for marker in ("请完成安全验证", "向右滑动完成验证", "人机验证")
        )
        if "账号或密码错误" in body or "用户名或密码错误" in body:
            return {"login_status": "failed", "block_reason": "invalid_credentials", "current_url": page.url}
        if "/user/login" not in page.url and "/user/signin" not in page.url:
            break
        page.wait_for_timeout(500)
    if page.is_closed():
        return {"login_status": "blocked", "block_reason": "browser_closed_before_login_completed"}

    _goto(page, destination)
    asin_input = _wait_for_sellersprite_asin_input(page, 12000)
    verified = bool(asin_input.count() and not asin_input.is_disabled())
    result = {"login_status": "verified" if verified else "blocked", "current_url": page.url}
    if not verified:
        result["block_reason"] = (
            "sellersprite_security_challenge_requires_user"
            if challenge_seen
            else _sellersprite_login_block_reason(page, asin_input)
        )
    return result


def login_sellersprite(payload: dict) -> dict:
    """Log in with transient or explicitly configured local credentials."""
    username, password, credential_source = _sellersprite_credentials(payload)
    if not username or not password:
        raise BrowserCollectionError("SellerSprite username and password are required")
    login_url = validate_url(payload.get("url") or "https://www.sellersprite.com/cn/w/user/login")
    destination = validate_url(
        payload.get("destination_url") or "https://www.sellersprite.com/v3/competitor-lookup"
    )
    sync_playwright = _require_playwright()
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(runtime, {**payload, "url": login_url})
        try:
            result = _login_sellersprite_in_page(
                page,
                username,
                password,
                destination,
                int(payload.get("manual_timeout_seconds", 180)),
            )
            result["profile_dir"] = str(profile)
            result["credential_source"] = credential_source
            return result
        finally:
            context.close()


def probe(payload: dict) -> dict:
    url = validate_url(payload.get("url"))
    sync_playwright = _require_playwright()
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(runtime, payload)
        try:
            _goto(page, url)
            challenge = _challenge_visible(page)
            if challenge and not payload.get("headless", False):
                challenge = not _wait_for_challenge_clearance(page, int(payload.get("manual_timeout_seconds", 120)))
            data = page.evaluate(
                """
                () => ({
                  tables: Array.from(document.querySelectorAll('table, [role="grid"]')).slice(0, 20).map((root, index) => ({
                    index,
                    headers: Array.from(root.querySelectorAll('thead th, [role="columnheader"]')).map(x => (x.innerText || x.textContent || '').trim()).filter(Boolean),
                    visibleRows: Array.from(root.querySelectorAll('tbody tr, [role="row"]')).filter(x => x.offsetWidth || x.offsetHeight).length
                  })),
                  inputs: Array.from(document.querySelectorAll('input, select')).slice(0, 100).map(x => ({
                    tag: x.tagName.toLowerCase(), type: x.type || null, name: x.name || null, id: x.id || null,
                    placeholder: x.placeholder || null, ariaLabel: x.getAttribute('aria-label')
                  })),
                  buttons: Array.from(document.querySelectorAll('button, [role="button"]')).filter(x => x.offsetWidth || x.offsetHeight).slice(0, 100).map(x => (x.innerText || x.textContent || '').trim()).filter(Boolean)
                })
                """
            )
            return {
                "probe_status": "blocked" if challenge else "complete",
                "url": page.url,
                "title": page.title(),
                "profile_dir": str(profile),
                **data,
            }
        finally:
            context.close()


def collect(payload: dict) -> dict:
    url = validate_url(payload.get("url"))
    extractor = payload.get("extractor")
    if extractor not in SUPPORTED_EXTRACTORS:
        raise BrowserCollectionError(f"extractor must be one of {sorted(SUPPORTED_EXTRACTORS)}")
    max_pages = max(1, min(int(payload.get("max_pages", 1)), MAX_PAGES))
    sync_playwright = _require_playwright()
    records = []
    pages = []
    errors = []
    coverage_complete = False
    with sync_playwright() as runtime:
        context, page, profile = _launch_context(runtime, payload)
        try:
            _goto(page, url)
            if _challenge_visible(page):
                cleared = False
                if not payload.get("headless", False):
                    cleared = _wait_for_challenge_clearance(page, int(payload.get("manual_timeout_seconds", 120)))
                if not cleared:
                    return {
                        "collection_status": "blocked",
                        "block_reason": "login_or_challenge_requires_user",
                        "records": [],
                        "profile_dir": str(profile),
                        "source_metadata": {"source": payload.get("source"), "url": page.url, "observed_at": _now_iso()},
                    }
            _run_actions(page, payload.get("interactions"))
            applied_filters = _read_filter_values(page, payload.get("filter_readbacks"))
            if extractor == "amazon_ranked_list":
                applied_filters.update(_ranked_list_identity(page.url))
            filter_verification = _filter_verification(payload.get("requested_filters"), applied_filters)
            next_selector = _next_selector(payload)
            seen_page_fingerprints = set()
            for page_number in range(1, max_pages + 1):
                if _challenge_visible(page):
                    errors.append({"page": page_number, "code": "LOGIN_OR_CHALLENGE"})
                    break
                if extractor == "amazon_ranked_list":
                    _expand_ranked_list(page)
                page_records = _extract_records(page, payload)
                fingerprint = json.dumps(
                    [(r.get("asin"), r.get("source_entity_id"), r.get("product_name")) for r in page_records[:10]],
                    sort_keys=True,
                    ensure_ascii=False,
                )
                if fingerprint in seen_page_fingerprints and page_number > 1:
                    errors.append({"page": page_number, "code": "REPEATED_PAGE"})
                    break
                seen_page_fingerprints.add(fingerprint)
                remaining = MAX_RECORDS - len(records)
                records.extend(page_records[:remaining])
                pages.append({"page": page_number, "url": page.url, "record_count": len(page_records)})
                if len(records) >= MAX_RECORDS:
                    errors.append({"page": page_number, "code": "RECORD_LIMIT"})
                    break
                if page_number >= max_pages:
                    coverage_complete = not _next_available(page, next_selector)
                    break
                body_prefix = ""
                try:
                    body_prefix = page.locator("body").inner_text(timeout=3000)[:1000]
                except Exception:
                    pass
                previous = page.url + "|" + body_prefix
                if not _click_next(page, next_selector, previous):
                    coverage_complete = True
                    break
            if extractor == "amazon_ranked_list":
                integrity = _rank_integrity(records)
                if integrity["missing_ranks"]:
                    errors.append(
                        {
                            "code": "RANK_GAPS",
                            "missing_count": len(integrity["missing_ranks"]),
                            "missing_ranks": integrity["missing_ranks"][:100],
                        }
                    )
                if integrity["duplicate_ranks"]:
                    errors.append(
                        {
                            "code": "DUPLICATE_RANKS",
                            "duplicate_ranks": integrity["duplicate_ranks"][:100],
                        }
                    )
            status = "complete" if not errors and coverage_complete else "partial"
            source_metadata = {
                "source": payload.get("source"),
                "page_kind": extractor,
                "marketplace": payload.get("marketplace"),
                "query": payload.get("query"),
                "page_title": page.title(),
                "location_profile": payload.get("location_profile"),
                "display_preferences": _display_preferences(payload),
                "observed_at": _now_iso(),
                "pages": pages,
                "coverage_complete": coverage_complete,
                "final_url": page.url,
                "profile_dir": str(profile),
            }
            result = {
                "collection_status": status,
                "filter_verification": filter_verification,
                "requested_filters": payload.get("requested_filters"),
                "applied_filters": applied_filters,
                "source_metadata": source_metadata,
                "records": records,
                "errors": errors,
                "counts": {"pages": len(pages), "records": len(records)},
            }
            output_path = payload.get("output_path")
            if output_path:
                target = Path(output_path).expanduser().resolve()
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.replace(target)
                result["output_path"] = str(target)
            return result
        finally:
            context.close()


def handle(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise BrowserCollectionError("input must be a JSON object")
    action = payload.get("skill_action")
    if action == "browser_status":
        return {"ok": True, "browser": browser_status()}
    if action == "browser_login":
        return {"ok": True, "browser": login(payload)}
    if action == "browser_probe":
        return {"ok": True, "browser": probe(payload)}
    if action == "collect_browser":
        return {"ok": True, "browser": collect(payload)}
    if action == "enrich_sellersprite_by_asin":
        return {"ok": True, "browser": collect_sellersprite_by_asin(payload)}
    raise BrowserCollectionError(f"unknown browser skill_action: {action}")
