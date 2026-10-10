#!/usr/bin/env python3
"""Verify visible product images and handoff-ready text in an exported workbook."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
DOC_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
XDR = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
DRAW = 'http://schemas.openxmlformats.org/drawingml/2006/main'
CELL_REF = re.compile(r'^([A-Z]+)(\d+)$')
INTERNAL_TEXT = re.compile(
    r'本次未附|原始开发文档|自有实拍|上传工作簿记载|待确认|待核对|待补充|'
    r'未提供|竞品图片不作为|不作为.{0,15}依据|需根据.{0,25}核对|'
    r'根据自有资料核对|销售变体|资料来源|证据状态'
)
VISIBLE_TEXT_COLUMNS = {'A', 'C', 'D', 'E', 'F'}
LISTING_RESEARCH_GAP = re.compile(r'未取得|未抓取|待验证|待复核|本地同义词候选|卖家精灵.{0,8}(?:不可用|失败|缺失)')
SIZE_PAIR = re.compile(r'(\d+(?:\.\d+)?)(?:\s*[–—−-]\s*(\d+(?:\.\d+)?))?\s*cm\s*/\s*(\d+(?:\.\d+)?)(?:\s*[–—−-]\s*(\d+(?:\.\d+)?))?\s*in\b', re.I)


def _target(base: str, value: str) -> str:
    if value.startswith('/'):
        return value.lstrip('/')
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), value))


def _relations(archive: ZipFile, owner: str) -> dict[str, str]:
    folder, filename = posixpath.split(owner)
    rels_path = posixpath.join(folder, '_rels', filename + '.rels')
    if rels_path not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read(rels_path))
    return {
        item.get('Id', ''): _target(owner, item.get('Target', ''))
        for item in root.findall(f'{{{PKG_REL}}}Relationship')
        if item.get('TargetMode') != 'External'
    }


def _shared_strings(archive: ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    return [
        ''.join(node.text or '' for node in item.iter(f'{{{MAIN}}}t'))
        for item in root.findall(f'{{{MAIN}}}si')
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    kind = cell.get('t')
    if kind == 'inlineStr':
        return ''.join(node.text or '' for node in cell.iter(f'{{{MAIN}}}t'))
    value = cell.find(f'{{{MAIN}}}v')
    if value is None or value.text is None:
        return ''
    if kind == 's':
        try:
            return shared[int(value.text)]
        except (IndexError, ValueError):
            return ''
    return value.text


def _product_sheet(archive: ZipFile) -> str:
    workbook_path = 'xl/workbook.xml'
    workbook = ET.fromstring(archive.read(workbook_path))
    relationships = _relations(archive, workbook_path)
    for sheet in workbook.findall(f'.//{{{MAIN}}}sheet'):
        if sheet.get('name') == '产品内容':
            path = relationships.get(sheet.get(f'{{{DOC_REL}}}id', ''))
            if path and path in archive.namelist():
                return path
    raise ValueError('missing 产品内容 worksheet')


def _listing_research_errors(archive: ZipFile, shared: list[str]) -> list[str]:
    errors = []
    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    relationships = _relations(archive, 'xl/workbook.xml')
    for entry in workbook.findall(f'.//{{{MAIN}}}sheet'):
        name = entry.get('name', '')
        if name == '产品内容' or name == '作图要求':
            continue
        path = relationships.get(entry.get(f'{{{DOC_REL}}}id', ''))
        if not path or path not in archive.namelist():
            continue
        sheet = ET.fromstring(archive.read(path))
        for row in sheet.findall(f'.//{{{MAIN}}}sheetData/{{{MAIN}}}row'):
            cells = {cell.get('r', ''): _cell_value(cell, shared).strip()
                     for cell in row.findall(f'{{{MAIN}}}c')}
            number = row.get('r', '')
            if cells.get(f'A{number}') != 'Search Terms':
                continue
            for address, value in cells.items():
                match = LISTING_RESEARCH_GAP.search(value)
                if match:
                    errors.append(f'{name}!{address} contains unverified Search Terms: {match.group()}')
    return errors


def _size_image_errors(archive: ZipFile, shared: list[str]) -> list[str]:
    workbook = ET.fromstring(archive.read('xl/workbook.xml'))
    relations = _relations(archive, 'xl/workbook.xml')
    errors = []
    for entry in workbook.findall(f'.//{{{MAIN}}}sheet'):
        if entry.get('name') != '作图要求':
            continue
        path = relations.get(entry.get(f'{{{DOC_REL}}}id', ''))
        if not path or path not in archive.namelist():
            continue
        sheet = ET.fromstring(archive.read(path))
        for row in sheet.findall(f'.//{{{MAIN}}}sheetData/{{{MAIN}}}row'):
            number = row.get('r', '')
            cells = {cell.get('r', ''): _cell_value(cell, shared).strip()
                     for cell in row.findall(f'{{{MAIN}}}c')}
            brief = next((value for address, value in cells.items()
                          if value and address != f'A{number}'
                          and re.search(r'(?:^|\n|[｜|])\s*(?:图片类型\s*[：:]\s*)?'
                                        r'(?:尺寸图|头围图|Product Size)(?=$|[\s。；：:｜|])',
                                        value, re.IGNORECASE)), '')
            if not brief:
                continue
            pairs = SIZE_PAIR.findall(brief)
            if not pairs:
                errors.append(f'作图要求 row {number} size image requires paired cm / in labels')
                continue
            for first_cm, second_cm, first_in, second_in in pairs:
                if bool(second_cm) != bool(second_in):
                    errors.append(f'作图要求 row {number} cm / in range endpoints differ')
                    continue
                endpoint_pairs = [(float(first_cm), float(first_in))]
                if second_cm:
                    endpoint_pairs.append((float(second_cm), float(second_in)))
                if any(abs(cm / 2.54 - inch) > 0.06 for cm, inch in endpoint_pairs):
                    errors.append(f'作图要求 row {number} cm / in conversion is incorrect')
    return errors


def _image_rows(archive: ZipFile, sheet_path: str, sheet: ET.Element) -> set[int]:
    rows = set()
    sheet_rels = _relations(archive, sheet_path)
    for drawing_ref in sheet.findall(f'.//{{{MAIN}}}drawing'):
        drawing_path = sheet_rels.get(drawing_ref.get(f'{{{DOC_REL}}}id', ''))
        if not drawing_path or drawing_path not in archive.namelist():
            continue
        drawing = ET.fromstring(archive.read(drawing_path))
        image_rels = _relations(archive, drawing_path)
        for anchor in drawing:
            origin = anchor.find(f'{{{XDR}}}from')
            if origin is None:
                continue
            col = origin.find(f'{{{XDR}}}col')
            row = origin.find(f'{{{XDR}}}row')
            if col is None or row is None or col.text != '1':
                continue
            pic = anchor.find(f'{{{XDR}}}pic')
            if pic is None:
                continue
            blip = pic.find(f'.//{{{DRAW}}}blip')
            if blip is None:
                continue
            media_path = image_rels.get(blip.get(f'{{{DOC_REL}}}embed', ''))
            if media_path and media_path in archive.namelist() and archive.getinfo(media_path).file_size:
                rows.add(int(row.text) + 1)
    return rows


def validate(path: Path) -> dict:
    errors = []
    try:
        with ZipFile(path) as archive:
            sheet_path = _product_sheet(archive)
            sheet = ET.fromstring(archive.read(sheet_path))
            shared = _shared_strings(archive)
            cells = {}
            for cell in sheet.findall(f'.//{{{MAIN}}}sheetData/{{{MAIN}}}row/{{{MAIN}}}c'):
                match = CELL_REF.fullmatch(cell.get('r', ''))
                if match:
                    cells[(match.group(1), int(match.group(2)))] = _cell_value(cell, shared).strip()
            product_rows = sorted(
                row for (column, row), value in cells.items()
                if column == 'A' and row >= 2 and value
            )
            if not product_rows:
                errors.append('产品内容 has no product rows')
            image_rows = _image_rows(archive, sheet_path, sheet)
            errors.extend(_listing_research_errors(archive, shared))
            errors.extend(_size_image_errors(archive, shared))
            for row in product_rows:
                if row not in image_rows:
                    errors.append(f'产品内容!B{row} has no embedded product image')
                for column in VISIBLE_TEXT_COLUMNS:
                    value = cells.get((column, row), '')
                    match = INTERNAL_TEXT.search(value)
                    if match:
                        errors.append(
                            f'产品内容!{column}{row} contains internal handoff text: {match.group()}'
                        )
    except (BadZipFile, KeyError, OSError, ET.ParseError, ValueError) as exc:
        errors.append(f'cannot inspect workbook: {exc}')
        product_rows = []
    return {'ready_for_delivery': not errors, 'product_rows': len(product_rows), 'errors': errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbooks', nargs='+', type=Path)
    args = parser.parse_args()
    reports = {str(path): validate(path) for path in args.workbooks}
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if all(item['ready_for_delivery'] for item in reports.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
