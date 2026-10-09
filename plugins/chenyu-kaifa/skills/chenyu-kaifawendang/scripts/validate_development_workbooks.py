"""Validate Chenyu one-product-per-workbook development Excel files."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"s": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}
RID = f"{{{REL_NS}}}id"

RESEARCH_HEADERS = {
    "站点",
    "上架日期",
    "Review数量",
    "售价（当地币种）",
    "大品类排名",
    "所在品类",
    "预估日销量",
    "产品优点&特征",
    "缺点",
    "生命周期",
    "ASIN",
    "亚马逊产品链接",
    "图片",
}
CONFIRM_HEADERS = {
    "图片",
    "名称",
    "备注说明",
    "SKU",
    "起订量",
    "交期（天）",
    "成本（元）",
    "重量（g）",
    "亚马逊链接",
    "ASIN",
    "图片/视频建议",
    "采购链接1",
    "供应商",
}
DETAIL_HEADERS = {"价格/克重", "变体", "产品属性", "产品主图/实拍图", "备注"}
FORBIDDEN_DETAIL_HEADERS = {"内容清单", "listing"}


def _relationships(package: zipfile.ZipFile, part: str) -> dict[str, str]:
    rel_name = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if rel_name not in package.namelist():
        return {}
    result = {}
    root = ET.fromstring(package.read(rel_name))
    for rel in root:
        target = rel.get("Target", "")
        if not target.startswith("/"):
            target = posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
        else:
            target = target.lstrip("/")
        result[rel.get("Id", "")] = target
    return result


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref or "")
    value = 0
    for char in letters.group(0) if letters else "":
        value = value * 26 + ord(char) - 64
    return value


def _sheet_rows(root: ET.Element, shared: list[str]) -> dict[int, dict[int, str]]:
    rows: dict[int, dict[int, str]] = {}
    for cell in root.findall("s:sheetData/s:row/s:c", NS):
        ref = cell.get("r", "")
        row_match = re.search(r"\d+", ref)
        if not row_match:
            continue
        row_number = int(row_match.group(0))
        value = cell.findtext("s:v", "", NS)
        if cell.get("t") == "s" and value:
            value = shared[int(value)]
        elif cell.get("t") == "inlineStr":
            value = "".join(node.text or "" for node in cell.findall(".//s:t", NS))
        elif cell.find("s:f", NS) is not None and not value:
            value = ""
        rows.setdefault(row_number, {})[_column_index(ref)] = value.strip()
    return rows


def _headers(rows: dict[int, dict[int, str]], row_numbers: tuple[int, ...]) -> set[str]:
    return {
        value
        for row_number in row_numbers
        for value in rows.get(row_number, {}).values()
        if value
    }


def inspect_workbook(path: Path, template: bool = False) -> dict:
    report = {"path": str(path.resolve()), "errors": [], "warnings": [], "sheets": []}
    if path.suffix.lower() != ".xlsx":
        report["errors"].append("只支持 .xlsx 文件")
        return report
    try:
        package = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        report["errors"].append(f"无法读取工作簿：{error}")
        return report

    with package:
        names = set(package.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [
                "".join(node.text or "" for node in item.findall(".//s:t", NS))
                for item in ET.fromstring(package.read("xl/sharedStrings.xml"))
            ]
        workbook = ET.fromstring(package.read("xl/workbook.xml"))
        workbook_rels = _relationships(package, "xl/workbook.xml")
        sheets = []
        for node in workbook.findall("s:sheets/s:sheet", NS):
            name = node.get("name", "")
            part = workbook_rels.get(node.get(RID, ""), "")
            if not part or part not in names:
                report["errors"].append(f"无法解析工作表：{name}")
                continue
            root = ET.fromstring(package.read(part))
            rows = _sheet_rows(root, shared)
            has_drawing = root.find("s:drawing", NS) is not None
            sheets.append({"name": name, "rows": rows, "has_drawing": has_drawing})
            report["sheets"].append({"name": name, "has_drawing": has_drawing})

        if len(sheets) != 3:
            report["errors"].append(f"应有 3 张工作表，实际为 {len(sheets)} 张")
            return report
        if [sheet["name"] for sheet in sheets[:2]] != ["参考产品信息调研", "产品确认"]:
            report["errors"].append("前两张表必须依次为“参考产品信息调研”“产品确认”")

        research_headers = _headers(sheets[0]["rows"], (1,))
        missing = sorted(RESEARCH_HEADERS - research_headers)
        if missing:
            report["errors"].append("参考产品信息调研缺少字段：" + "、".join(missing))

        confirm_headers = _headers(sheets[1]["rows"], (1,))
        missing = sorted(CONFIRM_HEADERS - confirm_headers)
        if missing:
            report["errors"].append("产品确认缺少字段：" + "、".join(missing))

        detail_headers = _headers(sheets[2]["rows"], (1, 2))
        missing = sorted(DETAIL_HEADERS - detail_headers)
        if missing:
            report["errors"].append("产品详情缺少字段：" + "、".join(missing))
        if not any("供应商产品" in header or header == "图片" for header in detail_headers):
            report["errors"].append("产品详情缺少供应商产品名称或图片字段")
        forbidden = sorted(FORBIDDEN_DETAIL_HEADERS & detail_headers)
        if forbidden:
            report["errors"].append("产品详情不应包含字段：" + "、".join(forbidden))

        research_rows = [
            row
            for row_number, row in sheets[0]["rows"].items()
            if row_number > 1 and any(value for value in row.values())
        ]
        if not template:
            if not research_rows:
                report["errors"].append("参考产品信息调研至少需要一条商品记录")
            for row in research_rows:
                if row.get(12) and not row.get(11):
                    report["errors"].append("参考商品链接缺少对应 ASIN")
                if row.get(12) and not any(row.get(column) for column in range(2, 8)):
                    report["errors"].append("参考商品只有链接，缺少已核实的调研数据")

        confirm_rows = [
            row
            for row_number, row in sheets[1]["rows"].items()
            if row_number > 1 and any(value for value in row.values())
        ]
        if template:
            if confirm_rows:
                report["warnings"].append("母版产品确认区包含示例值")
        elif len(confirm_rows) != 1:
            report["errors"].append(f"产品确认应只有 1 个产品记录，实际为 {len(confirm_rows)} 个")

        if not template and sheets[2]["name"] in {"产品详情", "产品详情母版", "Sheet3"}:
            report["errors"].append("第三张表必须改为当前产品简称")
        if not sheets[1]["has_drawing"]:
            report["warnings"].append("产品确认未检测到嵌入图片")
        if not sheets[2]["has_drawing"]:
            report["warnings"].append("产品详情未检测到嵌入图片")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--template", action="store_true", help="允许空白产品确认区和母版表名")
    args = parser.parse_args()
    reports = [inspect_workbook(path, template=args.template) for path in args.files]
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if any(report["errors"] for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
