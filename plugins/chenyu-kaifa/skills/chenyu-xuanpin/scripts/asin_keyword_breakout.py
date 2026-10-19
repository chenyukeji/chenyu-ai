"""Collect real SellerSprite ASIN reverse-keyword evidence and export selection results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from PIL import Image
from discovery_workbook import HEADERS, export_discovery_workbook

MARKET_IDS = {"US": 1, "DE": 4}
MARKET_STATIONS = {"US": {"US", "USA", "UNITED_STATES"}, "DE": {"DE", "GERMANY"}}
ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
MONTH_PATTERN = re.compile(r"^20\d{4}$")
API_PATH = "/v3/api/relation/reversing"


def number(value):
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def normalize_item(item):
    if not isinstance(item, dict) or not isinstance(item.get("keywords"), str):
        return None
    points = {}
    for point in item.get("searchesTrend") or []:
        if not isinstance(point, dict):
            continue
        month = str(point.get("month", ""))
        searches = number(point.get("searches"))
        if MONTH_PATTERN.fullmatch(month) and searches is not None and searches >= 0:
            points[month] = {"month": month, "searches": int(searches)}
    return {
        "keyword": item["keywords"].strip(),
        "translation": str(item.get("keywordCn") or "").strip(),
        "monthly_searches": number(item.get("searches")),
        "growth_percent": number(item.get("searchesGrowth")),
        "monthly_purchases": number(item.get("purchases")),
        "purchase_rate": number(item.get("purchaseRate")),
        "ppc": number(item.get("exactPpc")),
        "ppc_min": number(item.get("minExactPpc")),
        "ppc_max": number(item.get("maxExactPpc")),
        "advertising_competitors": number(item.get("latest7daysAds")),
        "products": number(item.get("products")),
        "title_density": number(item.get("titleDensityExact")),
        "traffic_percentage": number(item.get("trafficPercentage")),
        "trend": [points[key] for key in sorted(points)],
    }


def _product(page, market, asin):
    title = page.locator(".search-info .asin-info .title").first
    image = page.locator(".search-info .asin-img .img").first
    name = title.get_attribute("title") if title.count() else ""
    style = image.get_attribute("style") if image.count() else ""
    match = re.search(r'url\(["\']?([^"\')]+)', style or "")
    return {"asin": asin, "name": (name or "").strip()[:300],
            "url": f"https://www.amazon.{'com' if market == 'US' else 'de'}/dp/{asin}",
            "image_url": match.group(1) if match else ""}


def _valid_response(body, market, asin):
    if not isinstance(body, dict) or body.get("code") != "OK":
        return False
    data = body.get("data")
    return (isinstance(data, dict) and data.get("asin") == asin
            and data.get("station") in MARKET_STATIONS[market]
            and isinstance(data.get("items"), list))


def collect_reverse(market, asin, output, max_pages=20):
    """Read ordinary page pagination through the shared authenticated browser."""
    if market not in MARKET_IDS or not ASIN_PATTERN.fullmatch(asin):
        raise ValueError("只支持 US/DE 与有效 ASIN")
    if not 1 <= max_pages <= 40:
        raise ValueError("max_pages 必须为 1–40")
    import selection_collectors
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    url = "https://www.sellersprite.com/v3/keyword-reverse/?" + urlencode(
        {"marketId": MARKET_IDS[market], "q": asin})
    with selection_collectors.session({"headless": True}, url, sellersprite=True) as page:
        def matches(response):
            if API_PATH not in response.url or response.request.method != "POST":
                return False
            try:
                return json.loads(response.request.post_data or "{}").get("asin") == asin
            except ValueError:
                return False

        with page.expect_response(matches, timeout=30000) as pending:
            page.reload(wait_until="domcontentloaded")
        first = pending.value
        body = first.json() if first.status == 200 else {}
        if not _valid_response(body, market, asin):
            data = body.get("data") if isinstance(body, dict) else None
            raise RuntimeError("关键词反查结果与站点/ASIN不匹配："
                               f"HTTP={first.status}, code={body.get('code')}, "
                               f"asin={data.get('asin') if isinstance(data, dict) else None}, "
                               f"station={data.get('station') if isinstance(data, dict) else None}")
        request = json.loads(first.request.post_data)
        if request.get("limit") != 50 or request.get("skip") != 0:
            raise RuntimeError("关键词反查分页参数未核实")
        data = body["data"]
        items = list(data["items"])
        total = int(data.get("total") or 0)
        gaps = []
        for page_index in range(1, max_pages):
            if len(items) >= total:
                break
            request["skip"] = page_index * 50
            response = page.request.post(first.url, data=json.dumps(request),
                                         headers={"Content-Type": "application/json"}, timeout=30000)
            next_body = response.json() if response.status == 200 else {}
            if not _valid_response(next_body, market, asin):
                gaps.append(f"第 {page_index + 1} 页未取得匹配结果")
                break
            items.extend(next_body["data"]["items"])
        product = _product(page, market, asin)
        image_url = product["image_url"]
        if image_url.startswith("https://"):
            try:
                response = page.request.get(image_url, timeout=15000)
                image_bytes = response.body()
                if response.ok and len(image_bytes) <= 4 * 1024 * 1024:
                    with Image.open(BytesIO(image_bytes)) as opened:
                        opened.verify()
                    suffix = ".png" if "png" in response.headers.get("content-type", "") else ".jpg"
                    image_path = output.with_name(f"{output.stem}-product{suffix}")
                    image_path.write_bytes(image_bytes)
                    product["image_file"] = image_path.name
            except Exception:
                gaps.append("产品图未能下载，保留商品链接")
        records = {}
        for item in items:
            row = normalize_item(item)
            if row and row["keyword"]:
                records[row["keyword"].casefold()] = row
        result = {"marketplace": market, "asin": asin, "product": product,
                  "source_url": page.url, "observed_at": datetime.now(timezone.utc).isoformat(),
                  "reported_total": total, "collected_count": len(records),
                  "status": "complete" if len(items) >= total and not gaps else "partial",
                  "gaps": gaps + ([f"仅覆盖前 {len(items)}/{total} 条"] if len(items) < total else []),
                  "keywords": list(records.values())}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _selected_rows(evidence_paths, selection_path):
    evidence = {}
    for path in evidence_paths:
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        evidence[(data["marketplace"], data["asin"])] = (data, source.parent)
    selected = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    if not isinstance(selected, list) or not selected:
        raise ValueError("selection 必须是非空数组")
    rows = []
    for choice in selected:
        key = (choice.get("marketplace"), choice.get("asin"))
        if key not in evidence:
            raise ValueError(f"缺少 {key} 的反查证据")
        data, folder = evidence[key]
        match = next((row for row in data["keywords"]
                      if row["keyword"].casefold() == str(choice.get("keyword", "")).casefold()), None)
        if not match:
            raise ValueError(f"反查证据没有关键词 {choice.get('keyword')}")
        product = data["product"]
        rows.append({**match, "direction": str(choice.get("direction") or "")[:80],
                     "note": str(choice.get("note") or "")[:240],
                     "marketplace": key[0], "asin": key[1], "product": product,
                     "image_path": folder / product["image_file"] if product.get("image_file") else None,
                     "source_url": data["source_url"], "observed_at": data["observed_at"],
                     "coverage": f"{data['collected_count']}/{data['reported_total']}"})
    return rows


def render(evidence_paths, selection_path, output_dir):
    """Export one product-result sheet; detailed keyword evidence stays in input JSON."""
    selected = _selected_rows(evidence_paths, selection_path)
    products = {}
    local_images = {}
    for row in selected:
        key = (row["marketplace"], row["asin"])
        if key not in products:
            product = row["product"]
            result = {header: product.get(header) for header in HEADERS}
            result.update({"站点": key[0], "ASIN": key[1],
                           "亚马逊产品链接": product.get("url", ""), "图片": ""})
            # Keyword intent is not a product attribute or a sales estimate.
            if not result["产品优点&特征"] and product.get("name"):
                result["产品优点&特征"] = product["name"]
            image_path = row["image_path"]
            if image_path and image_path.is_file():
                image_key = str(image_path.resolve())
                local_images[image_key] = image_path
                result["图片"] = image_key
            products[key] = (result, [])
        result, reasons = products[key]
        metrics = []
        for field, label in (("monthly_searches", "月搜索量"),
                             ("growth_percent", "搜索增长率(%)"), ("ppc", "PPC")):
            if row.get(field) is not None:
                metrics.append(f"{label} {row[field]:g}")
        reason = f"关键词 {row['keyword']}" + ("：" + "，".join(metrics) if metrics else "")
        if row["note"]:
            reason += "；" + row["note"]
        if reason not in reasons:
            reasons.append(reason)
    results = []
    for result, reasons in products.values():
        result["理由"] = "\n".join(filter(None, [result.get("理由"), *reasons]))
        results.append(result)

    def load_local_image(key):
        path = local_images[key]
        with Image.open(path) as image:
            extension = {"JPEG": "jpg", "PNG": "png", "GIF": "gif"}.get(image.format)
            image.verify()
        if not extension:
            raise ValueError("不支持的产品图片格式")
        return path.read_bytes(), extension

    output_dir = Path(output_dir)
    exported = export_discovery_workbook(output_dir / "开品结果.xlsx", results,
                                         image_loader=load_local_image, headers=HEADERS)
    return {"workbook": exported["path"], "rows": len(results),
            "image_failure_count": exported["image_failure_count"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--market", choices=MARKET_IDS, required=True)
    collect.add_argument("--asin", required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--max-pages", type=int, default=20)
    report = sub.add_parser("render")
    report.add_argument("--evidence", type=Path, action="append", required=True)
    report.add_argument("--selection", type=Path, required=True)
    report.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = (collect_reverse(args.market, args.asin.upper(), args.output, args.max_pages)
              if args.action == "collect" else render(args.evidence, args.selection, args.output_dir))
    print(json.dumps(result if args.action == "render" else {
        "marketplace": result["marketplace"], "asin": result["asin"], "status": result["status"],
        "collected_count": result["collected_count"], "reported_total": result["reported_total"],
        "evidence": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
