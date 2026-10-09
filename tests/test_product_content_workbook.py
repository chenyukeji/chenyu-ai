import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-yunying'
MASTER = ROOT / 'skills/chenyu-yunying/assets/晨玙Amazon运营交付大母版.xlsx'
SCRIPT = ROOT / 'skills/chenyu-yunying/scripts/validate_product_content_workbook.py'
SPEC = importlib.util.spec_from_file_location('validate_product_content_workbook', SCRIPT)
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


def altered_workbook(destination, mutate, worksheet="xl/worksheets/sheet1.xml"):
    with ZipFile(MASTER) as source, ZipFile(destination, 'w') as output:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == worksheet:
                content = mutate(content)
            output.writestr(item, content)


def test_master_product_row_has_real_embedded_image():
    result = VALIDATOR.validate(MASTER)
    assert result['ready_for_delivery'], result['errors']
    assert result['product_rows'] == 1


def test_missing_product_image_is_rejected():
    def remove_drawing(content):
        root = ET.fromstring(content)
        for drawing in root.findall(f'{{{MAIN}}}drawing'):
            root.remove(drawing)
        return ET.tostring(root, encoding='utf-8')

    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'missing-image.xlsx'
        altered_workbook(path, remove_drawing)
        result = VALIDATOR.validate(path)
    assert not result['ready_for_delivery']
    assert any('产品内容!B2 has no embedded product image' in error
               for error in result['errors'])


def test_internal_uncertainty_note_is_rejected():
    def add_note(content):
        root = ET.fromstring(content)
        cell = root.find(f'.//{{{MAIN}}}c[@r="F2"]')
        for child in list(cell):
            cell.remove(child)
        cell.set('t', 'inlineStr')
        inline = ET.SubElement(cell, f'{{{MAIN}}}is')
        ET.SubElement(inline, f'{{{MAIN}}}t').text = '本次未附原始开发文档，需根据自有资料核对'
        return ET.tostring(root, encoding='utf-8')

    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'internal-note.xlsx'
        altered_workbook(path, add_note)
        result = VALIDATOR.validate(path)
    assert not result['ready_for_delivery']
    assert any('产品内容!F2 contains internal handoff text' in error
               for error in result['errors'])


def test_unverified_search_terms_note_is_rejected():
    def add_note(content):
        root = ET.fromstring(content)
        cell = root.find(f'.//{{{MAIN}}}c[@r="D10"]')
        for child in list(cell):
            cell.remove(child)
        cell.set('t', 'inlineStr')
        inline = ET.SubElement(cell, f'{{{MAIN}}}is')
        ET.SubElement(inline, f'{{{MAIN}}}t').text = (
            '本地同义词候选；未取得卖家精灵反查及 Amazon 前20自然结果，待验证'
        )
        return ET.tostring(root, encoding='utf-8')

    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'unverified-search-terms.xlsx'
        altered_workbook(path, add_note, 'xl/worksheets/sheet3.xml')
        result = VALIDATOR.validate(path)
    assert not result['ready_for_delivery']
    assert any('DE Listing!D10 contains unverified Search Terms' in error
               for error in result['errors'])


def test_size_image_without_inches_is_rejected():
    def cm_only(content):
        root = ET.fromstring(content)
        cell = root.find(f'.//{{{MAIN}}}c[@r="G4"]')
        for child in list(cell):
            cell.remove(child)
        cell.set('t', 'inlineStr')
        inline = ET.SubElement(cell, f'{{{MAIN}}}is')
        ET.SubElement(inline, f'{{{MAIN}}}t').text = (
            '第三张｜尺寸图。头围用闭合测量环，唯一上图数值 45–60 cm。'
        )
        return ET.tostring(root, encoding='utf-8')

    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'cm-only.xlsx'
        altered_workbook(path, cm_only, 'xl/worksheets/sheet2.xml')
        result = VALIDATOR.validate(path)
    assert not result['ready_for_delivery']
    assert any('size image requires paired cm / in labels' in error
               for error in result['errors'])
