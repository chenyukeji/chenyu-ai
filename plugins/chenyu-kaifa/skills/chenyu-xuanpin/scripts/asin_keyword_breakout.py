"""Collect real SellerSprite ASIN reverse-keyword trends and render a product-linked report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont, ImageOps
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

MARKET_IDS = {"US": 1, "DE": 4}
MARKET_STATIONS = {"US": {"US", "USA", "UNITED_STATES"}, "DE": {"DE", "GERMANY"}}
ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
MONTH_PATTERN = re.compile(r"^20\d{4}$")
API_PATH = "/v3/api/relation/reversing"
FONT_PATH = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")


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


def sparkline(points, width=166, height=58):
    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    values = [int(item["searches"]) for item in points if isinstance(item.get("searches"), (int, float))][-36:]
    draw.line((5, height-5, width-5, height-5), fill="#e6eaf0")
    if len(values) < 2:
        return image
    scale = max(values) or 1
    coords = [(5 + i * (width-10) / (len(values)-1), height-6 - value * (height-14) / scale)
              for i, value in enumerate(values)]
    draw.polygon([(coords[0][0], height-5), *coords, (coords[-1][0], height-5)], fill="#fff1e4")
    draw.line(coords, fill="#f58b29", width=2, joint="curve")
    return image


def _font(size):
    return ImageFont.truetype(str(FONT_PATH), size) if FONT_PATH.exists() else ImageFont.load_default()


def _formatted(value, decimals=0):
    return "—" if value is None else f"{value:,.{decimals}f}"


def _image(path, size=(72, 72)):
    if not path or not Path(path).is_file():
        return None
    with Image.open(path) as opened:
        return ImageOps.contain(opened.convert("RGB"), size)


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
    """Render only selected source-backed words, with a separate raw-month sheet."""
    rows = _selected_rows(evidence_paths, selection_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "长尾词趋势"
    headers = ["站点", "产品方向", "关键词", "中文含义", "月搜索趋势", "月搜索量", "增长率", "月购买量",
               "PPC竞价", "广告竞品数", "商品数", "产品图", "对应竞品", "ASIN", "产品链接", "证据覆盖", "说明"]
    sheet.append(headers)
    for index, width in enumerate([8, 19, 30, 18, 25, 16, 13, 16, 14, 15, 13, 14, 48, 17, 42, 14, 38], 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="E9EDF3")
        cell.font = Font(bold=True, color="26364D")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = f"A1:Q{len(rows)+1}"
    monthly = workbook.create_sheet("逐月搜索量原始点")
    monthly.append(["站点", "ASIN", "关键词", "月份", "搜索量", "数据来源", "采集时间"])
    for col, width in {"A": 9, "B": 17, "C": 32, "D": 12, "E": 14, "F": 72, "G": 30}.items():
        monthly.column_dimensions[col].width = width
    monthly.freeze_panes = "D2"
    preview = Image.new("RGB", (1600, 100 + 105 * min(len(rows), 20)), "#ffffff")
    draw = ImageDraw.Draw(preview)
    label_font, small_font = _font(16), _font(12)
    draw.text((25, 17), "ASIN 关键词反查 · 长尾词趋势选品", font=_font(20), fill="#243750")
    draw.text((25, 55), "每行对应真实反查词与竞品；折线为卖家精灵逐月搜索量。历史 0 可能低于收录阈值。",
              font=small_font, fill="#66788f")
    for index, row in enumerate(rows, 2):
        values = [row["marketplace"], row["direction"], row["keyword"], row["translation"], "",
                  row["monthly_searches"], row["growth_percent"], row["monthly_purchases"], row["ppc"],
                  row["advertising_competitors"], row["products"], "", row["product"]["name"],
                  row["asin"], row["product"]["url"], row["coverage"], row["note"]]
        sheet.append(values)
        for point in row["trend"]:
            monthly.append([row["marketplace"], row["asin"], row["keyword"], point["month"],
                            point["searches"], row["source_url"], row["observed_at"]])
        sheet.row_dimensions[index].height = 70
        for cell in sheet[index]:
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if index % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F8FAFD")
        sheet.cell(index, 15).hyperlink = row["product"]["url"]
        sheet.cell(index, 15).font = Font(color="245BD5", underline="single")
        for col, fmt in {6: '#,##0', 7: '0.00"%"', 8: '#,##0', 9: '0.00'}.items():
            sheet.cell(index, col).number_format = fmt
        chart = sparkline(row["trend"])
        buffer = BytesIO()
        chart.save(buffer, format="PNG")
        buffer.seek(0)
        excel_chart = ExcelImage(buffer)
        excel_chart.width, excel_chart.height = chart.size
        sheet.add_image(excel_chart, f"E{index}")
        product_image = _image(row["image_path"])
        if product_image:
            buffer = BytesIO()
            product_image.save(buffer, format="PNG")
            buffer.seek(0)
            excel_product = ExcelImage(buffer)
            excel_product.width, excel_product.height = product_image.size
            sheet.add_image(excel_product, f"L{index}")
        if index <= 21:
            y = 100 + (index-2) * 105
            draw.rectangle((15, y, 1585, y+101), fill="#f8fafc" if index % 2 == 0 else "#ffffff")
            draw.line((15, y+101, 1585, y+101), fill="#e6eaf0")
            draw.text((30, y+15), row["keyword"][:33], font=label_font, fill="#243750")
            draw.text((30, y+49), (row["direction"] or row["translation"])[:25],
                      font=small_font, fill="#67788d")
            preview.paste(chart.resize((215, 65)), (420, y+5))
            if row["trend"]:
                draw.text((425, y+75), f"{row['trend'][0]['month']} → {row['trend'][-1]['month']}",
                          font=small_font, fill="#718096")
            draw.text((665, y+15), "月搜索 " + _formatted(row["monthly_searches"]),
                      font=small_font, fill="#243750")
            draw.text((665, y+50), "增长 " + _formatted(row["growth_percent"], 1) +
                      "%  ·  PPC " + _formatted(row["ppc"], 2), font=small_font, fill="#d36c15")
            if product_image:
                preview.paste(product_image, (940, y+15))
            name = row["product"]["name"]
            draw.text((1030, y+10), name[:48], font=small_font, fill="#243750")
            if len(name) > 48:
                draw.text((1030, y+31), name[48:96], font=small_font, fill="#243750")
            draw.text((1030, y+60), f"{row['marketplace']} · {row['asin']}",
                      font=small_font, fill="#66788f")
    workbook_path = output_dir / "长尾词趋势选品.xlsx"
    preview_path = output_dir / "长尾词趋势选品.png"
    workbook.save(workbook_path)
    preview.save(preview_path)
    return {"workbook": str(workbook_path), "preview": str(preview_path), "rows": len(rows)}


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
