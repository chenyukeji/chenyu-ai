"""Conservative row candidates, never a final image count or task assignment."""
import re
import unicodedata
from collections import defaultdict


NUMBER = r'[零一二两三四五六七八九十百\d]+'
ORDINAL = re.compile(r'(?:第\s*' + NUMBER + r'\s*[张幅]|图\s*' + NUMBER + r')')
NAMED = re.compile(r'(?:主图|尺寸图|功能图|细节图|场景图|卖点图|对比图|安装图|使用图|包装图)(?:\s*' + NUMBER + r')?')
HEADERS = {'序号', '图序', '图号', '图片顺序', '图片序号', '编号'}
REQUIREMENT_HEADERS = {'要求', '作图要求', '拍图要求', '拍图需求', '图片要求', '需求', '画面要求'}
REQUEST = re.compile(r'(?:做|制作|生成|设计|绘制|输出)(?:出)?\s*[一二两三四五六七八九十\d]+\s*[张幅]')


def normalized(value):
    return unicodedata.normalize('NFKC', str(value)).strip()


def location(cell):
    match = re.fullmatch(r'([A-Z]+)(\d+)', cell)
    return match[1], int(match[2])


def section_type(value):
    value = re.sub(r'\s+', '', normalized(value)).upper().rstrip(':：')
    if re.fullmatch(r'(?:(?:FR|DE|IT|ES|UK|US))?A\+(?:要求|作图要求|图片|模块|模块要求)?', value):
        return 'aplus'
    if value in {'普通图册', '普通图', '图册', '作图要求', '拍图需求'}:
        return 'gallery'
    return None


def add_candidates(sheet):
    rows = defaultdict(list)
    for cell in sheet['cells']:
        rows[location(cell['cell'])[1]].append(cell)
    marker_candidates, row_candidates, sections = [], [], []
    serial_columns, requirement_columns = set(), set()
    section = section_type(sheet['name'])
    for row, cells in sorted(rows.items()):
        markers, requirement_cells, row_sections = [], [], []
        for cell in cells:
            column, _ = location(cell['cell'])
            value = normalized(cell['value'])
            kind = section_type(value)
            # Generic requirement headers inside an A+ sheet are not a
            # transition back to gallery; only an explicit gallery label is.
            if section == 'aplus' and value in {'作图要求', '拍图需求'}:
                kind = None
            if kind:
                section = kind
                row_sections.append(cell)
                sections.append({**cell, 'row': row, 'content_type': kind})
            if value in HEADERS:
                serial_columns.add(column)
            if value in REQUIREMENT_HEADERS:
                requirement_columns.add(column)
            marker_kind = None
            if ORDINAL.fullmatch(value):
                marker_kind = 'explicit_ordinal'
            elif NAMED.fullmatch(value):
                marker_kind = 'image_type_label'
            elif column in serial_columns and re.fullmatch(r'[1-9]\d*(?:\.0+)?', value):
                marker_kind = 'number_in_serial_column'
            if marker_kind:
                markers.append({**cell, 'marker_kind': marker_kind})
            # Keep explicit requests as candidates even without an ordinal.
            # The agent must distinguish continuations, references and slots.
            if REQUEST.search(value):
                requirement_cells.append(cell['cell'])
        # An established requirement column can contain short unnumbered briefs.
        # Section headings/notes alone must not become extra image tasks.
        if not row_sections:
            for cell in cells:
                column, _ = location(cell['cell'])
                value = normalized(cell['value'])
                if (column in requirement_columns and value not in REQUIREMENT_HEADERS
                        and value and not re.match(r'^(?:注意|备注|说明|整体|整套|统一|共用|共享)', value)
                        and cell['cell'] not in requirement_cells):
                    requirement_cells.append(cell['cell'])
        if markers or requirement_cells:
            row_candidates.append({
                'row': row, 'content_type': section or 'unknown',
                'marker_cells': [c['cell'] for c in markers],
                'requirement_cells': requirement_cells,
                'evidence_cells': list(dict.fromkeys([c['cell'] for c in markers] + requirement_cells)),
                'inferred_order': len(row_candidates) + 1,
                'requires_semantic_review': True,
            })
            marker_candidates.extend(markers)
    sheet['task_marker_candidates'] = marker_candidates
    sheet['task_row_candidates'] = row_candidates
    sheet['section_candidates'] = sections
