"""Create a ranked discovery workbook with embedded product images."""
from __future__ import annotations

import json
import math
import posixpath
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr


HEADERS = [
    "站点", "上架日期", "Review数量", "售价（当地币种）", "大品类排名", "所在品类", "预估月销量",
    "产品优点&特征", "缺点", "生命周期", "ASIN", "亚马逊产品链接", "图片", "结论", "理由",
]


class WorkbookError(ValueError):
    pass


SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
RID_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _text(value) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value or ""))


def _cell(ref: str, value, style=2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{_text(value)}</t></is></c>'


def _conclusion_style(value) -> int:
    text = str(value or "")
    if "强开" in text or text.endswith("开") or "条件开" in text:
        return 4
    if "偏弱" in text or "观察" in text:
        return 5
    if "不建议" in text:
        return 6
    return 3


def _image_type(data: bytes, content_type: str | None = None) -> str | None:
    lowered = str(content_type or "").casefold()
    if data.startswith(b"\xff\xd8\xff") or "jpeg" in lowered or "jpg" in lowered:
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n") or "png" in lowered:
        return "png"
    if data.startswith((b"GIF87a", b"GIF89a")) or "gif" in lowered:
        return "gif"
    return None


def _download_image(url: str) -> tuple[bytes, str]:
    # Amazon search pages often return a URL whose path ends in a JPEG name but
    # whose transformation requests WebP (for example ``._AC_UL480_FMwebp_QL65_.jpg``).
    # Excel cannot embed that response as JPEG, so request Amazon's original image.
    url = re.sub(
        r"\._[^/]+_\.(jpe?g|png)(?=\?|$)",
        r".\1",
        str(url),
        flags=re.IGNORECASE,
    )
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=8) as response:
        data = response.read(8 * 1024 * 1024 + 1)
        content_type = response.headers.get("Content-Type")
    if not data or len(data) > 8 * 1024 * 1024:
        raise WorkbookError("image is empty or larger than 8 MB")
    extension = _image_type(data, content_type)
    if not extension:
        raise WorkbookError("image format is not supported for Excel embedding")
    return data, extension


def _relationship_targets(package: zipfile.ZipFile, rels_path: str) -> dict[str, str]:
    root = ET.fromstring(package.read(rels_path))
    return {
        item.get("Id"): item.get("Target")
        for item in root.findall(f"{{{REL_NS}}}Relationship")
        if item.get("Id") and item.get("Target")
    }


def _cell_value(cell: ET.Element) -> str:
    inline = "".join(item.text or "" for item in cell.findall(f".//{{{SHEET_NS}}}t"))
    if inline:
        return inline.strip()
    value = cell.find(f"{{{SHEET_NS}}}v")
    return (value.text or "").strip() if value is not None else ""


def _embedded_images_by_product(workbook_path: str | Path | None) -> dict[tuple[str, str], dict]:
    """Read already embedded images from an earlier workbook without extracting files."""
    if not workbook_path:
        return {}
    path = Path(workbook_path).expanduser().resolve()
    if not path.is_file():
        return {}
    try:
        with zipfile.ZipFile(path) as package:
            sheet_path = "xl/worksheets/sheet1.xml"
            sheet_root = ET.fromstring(package.read(sheet_path))
            drawing = sheet_root.find(f"{{{SHEET_NS}}}drawing")
            if drawing is None:
                return {}
            drawing_rel_id = drawing.get(f"{{{RID_NS}}}id")
            sheet_rels_path = "xl/worksheets/_rels/sheet1.xml.rels"
            drawing_target = _relationship_targets(package, sheet_rels_path).get(drawing_rel_id)
            if not drawing_target:
                return {}
            drawing_path = posixpath.normpath(
                posixpath.join(posixpath.dirname(sheet_path), drawing_target)
            ).lstrip("/")
            drawing_rels_path = posixpath.join(
                posixpath.dirname(drawing_path),
                "_rels",
                posixpath.basename(drawing_path) + ".rels",
            )
            image_targets = _relationship_targets(package, drawing_rels_path)

            row_values: dict[int, dict[str, str]] = {}
            for cell in sheet_root.findall(f".//{{{SHEET_NS}}}c"):
                ref = cell.get("r") or ""
                match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                if not match or match.group(1) not in {"A", "K"}:
                    continue
                row_values.setdefault(int(match.group(2)), {})[match.group(1)] = _cell_value(cell)

            drawing_root = ET.fromstring(package.read(drawing_path))
            cached = {}
            for anchor in drawing_root.findall(f"{{{DRAWING_NS}}}oneCellAnchor"):
                row_node = anchor.find(f"{{{DRAWING_NS}}}from/{{{DRAWING_NS}}}row")
                blip = anchor.find(f".//{{{DRAWINGML_NS}}}blip")
                if row_node is None or blip is None or row_node.text is None:
                    continue
                excel_row = int(row_node.text) + 1
                identity = row_values.get(excel_row, {})
                site = str(identity.get("A") or "").strip().upper()
                asin = str(identity.get("K") or "").strip().upper()
                relationship_id = blip.get(f"{{{RID_NS}}}embed")
                image_target = image_targets.get(relationship_id)
                if not site or not asin or not image_target:
                    continue
                media_path = posixpath.normpath(
                    posixpath.join(posixpath.dirname(drawing_path), image_target)
                ).lstrip("/")
                data = package.read(media_path)
                extension = _image_type(data)
                if extension:
                    cached[(site, asin)] = {"data": data, "extension": extension}
            return cached
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ET.ParseError):
        return {}


def _row_image_key(row: dict) -> tuple[str, str] | None:
    site = str(row.get("站点") or "").strip().upper()
    asin = str(row.get("ASIN") or "").strip().upper()
    return (site, asin) if site and asin else None


def _collect_images(
    rows: list[dict],
    image_loader,
    cached_images: dict[tuple[str, str], dict] | None = None,
) -> tuple[dict[int, dict], list[int], dict]:
    targets = {index: str(row.get("图片")) for index, row in enumerate(rows) if row.get("图片")}
    if not targets:
        return {}, [], {"reused": 0, "downloaded": 0, "unique_fetches": 0}
    embedded = {}
    failures = []
    cached_images = cached_images or {}
    reused_indexes = set()
    pending_by_url: dict[str, list[int]] = {}
    for index, url in targets.items():
        cached = cached_images.get(_row_image_key(rows[index]))
        if cached:
            embedded[index] = cached
            reused_indexes.add(index)
        else:
            pending_by_url.setdefault(url, []).append(index)
    if pending_by_url:
        with ThreadPoolExecutor(max_workers=min(12, len(pending_by_url))) as pool:
            futures = {pool.submit(image_loader, url): url for url in pending_by_url}
            for future in as_completed(futures):
                url = futures[future]
                indexes = pending_by_url[url]
                try:
                    data, extension = future.result()
                    for index in indexes:
                        embedded[index] = {"data": data, "extension": extension}
                except Exception:
                    failures.extend(indexes)
    return embedded, sorted(failures), {
        "reused": len(reused_indexes),
        "downloaded": sum(1 for index in embedded if index not in reused_indexes),
        "unique_fetches": len(pending_by_url),
    }


def _drawing_parts(rows: list[dict], embedded: dict[int, dict]) -> tuple[str, str, list[tuple[str, bytes]]]:
    anchors = []
    relationships = []
    media = []
    for image_number, row_index in enumerate(sorted(embedded), start=1):
        item = embedded[row_index]
        media_name = f"image{image_number}.{item['extension']}"
        relationship_id = f"rId{image_number}"
        title = str(rows[row_index].get("产品名称") or rows[row_index].get("ASIN") or f"产品图{image_number}")
        anchors.append(
            f'''<xdr:oneCellAnchor>
  <xdr:from><xdr:col>12</xdr:col><xdr:colOff>95250</xdr:colOff><xdr:row>{row_index + 1}</xdr:row><xdr:rowOff>95250</xdr:rowOff></xdr:from>
  <xdr:ext cx="1238250" cy="857250"/>
  <xdr:pic>
    <xdr:nvPicPr><xdr:cNvPr id="{image_number}" name={quoteattr(title)}/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>
    <xdr:blipFill><a:blip r:embed="{relationship_id}"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>
    <xdr:spPr><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>
  </xdr:pic>
  <xdr:clientData/>
</xdr:oneCellAnchor>'''
        )
        relationships.append(
            f'<Relationship Id="{relationship_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{media_name}"/>'
        )
        media.append((f"xl/media/{media_name}", item["data"]))
    drawing = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">{''.join(anchors)}</xdr:wsDr>'''
    rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(relationships)}</Relationships>'''
    return drawing, rels, media


def export_discovery_workbook(
    output_path: str | Path,
    rows: list[dict],
    image_loader=None,
    reuse_workbook_path: str | Path | None = None,
) -> dict:
    if not isinstance(rows, list):
        raise WorkbookError("rows must be a list")
    rows = sorted(rows, key=lambda row: -float(row.get("得分") or 0))
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    cache_source = reuse_workbook_path or (output if output.exists() else None)
    cached_images = _embedded_images_by_product(cache_source)
    embedded, image_failures, image_stats = _collect_images(
        rows,
        image_loader or _download_image,
        cached_images,
    )

    hyperlink_rels = []
    hyperlinks = []
    xml_rows = []
    header_cells = "".join(_cell(f"{_column_name(i)}1", header, 1) for i, header in enumerate(HEADERS, start=1))
    xml_rows.append(f'<row r="1" ht="32" customHeight="1">{header_cells}</row>')
    for row_index, row in enumerate(rows):
        row_number = row_index + 2
        cells = []
        for column_number, header in enumerate(HEADERS, start=1):
            ref = f"{_column_name(column_number)}{row_number}"
            value = row.get(header)
            if header == "图片":
                value = "" if row_index in embedded else ("图片未嵌入" if value else "")
            style = _conclusion_style(value) if header == "结论" else 2
            cells.append(_cell(ref, value, style))
            if header == "亚马逊产品链接" and value:
                relationship_id = f"rId{len(hyperlink_rels) + 1}"
                hyperlink_rels.append((relationship_id, str(value)))
                hyperlinks.append((ref, relationship_id))
        xml_rows.append(f'<row r="{row_number}" ht="105" customHeight="1">{"".join(cells)}</row>')

    widths = [8, 13, 11, 15, 12, 16, 13, 28, 27, 24, 14, 31, 22, 15, 55]
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    hyperlink_xml = ""
    if hyperlinks:
        hyperlink_xml = "<hyperlinks>" + "".join(
            f'<hyperlink ref="{ref}" r:id="{relationship_id}"/>' for ref, relationship_id in hyperlinks
        ) + "</hyperlinks>"
    sheet_relationships = [
        f'<Relationship Id="{relationship_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target={quoteattr(target)} TargetMode="External"/>'
        for relationship_id, target in hyperlink_rels
    ]
    drawing_rel_id = None
    drawing_xml = drawing_rels = None
    media = []
    if embedded:
        drawing_rel_id = f"rId{len(sheet_relationships) + 1}"
        sheet_relationships.append(
            f'<Relationship Id="{drawing_rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
        )
        drawing_xml, drawing_rels, media = _drawing_parts(rows, embedded)
    drawing_tag = f'<drawing r:id="{drawing_rel_id}"/>' if drawing_rel_id else ""
    last_row = max(1, len(rows) + 1)
    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="18"/>
  <cols>{cols}</cols>
  <sheetData>{''.join(xml_rows)}</sheetData>
  <autoFilter ref="A1:O{last_row}"/>
  {hyperlink_xml}
  <pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  {drawing_tag}
</worksheet>'''
    sheet_rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(sheet_relationships)}</Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="3"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts>
  <fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFC6E0B4"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FF33A36B"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFD966"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4CCCC"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FF666666"/></left><right style="thin"><color rgb="FF666666"/></right><top style="thin"><color rgb="FF666666"/></top><bottom style="thin"><color rgb="FF666666"/></bottom><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="7">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="1" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="开品结果" sheetId="1" r:id="rId1"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>'''
    workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    package_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    drawing_override = '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>' if embedded else ""
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="jpg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/><Default Extension="gif" ContentType="image/gif"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{drawing_override}</Types>'''

    temporary = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", package_rels)
        package.writestr("xl/workbook.xml", workbook)
        package.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        package.writestr("xl/styles.xml", styles)
        package.writestr("xl/worksheets/sheet1.xml", worksheet)
        if sheet_relationships:
            package.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels)
        if embedded:
            package.writestr("xl/drawings/drawing1.xml", drawing_xml)
            package.writestr("xl/drawings/_rels/drawing1.xml.rels", drawing_rels)
            for media_path, data in media:
                package.writestr(media_path, data)
    temporary.replace(output)
    return {
        "path": str(output), "sheet": "开品结果", "row_count": len(rows), "sorted_by": "得分 desc",
        "embedded_image_count": len(embedded), "image_failure_count": len(image_failures),
        "reused_image_count": image_stats["reused"],
        "downloaded_image_count": image_stats["downloaded"],
        "unique_image_fetch_count": image_stats["unique_fetches"],
    }
