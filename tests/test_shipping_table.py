import importlib.util
from pathlib import Path
import pytest
from openpyxl import load_workbook
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-wuliu/skills/chenyu-xiangmai-fapiao/scripts/generate_shipping_table.py'
spec = importlib.util.spec_from_file_location('shipping_table', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def data():
    return {'cartons': [{'sourcePhotos': ['photo.jpg'], 'weightKg': 16.05, 'items': [
        {'nameZh': '装备A', 'rawText': '装备A=12', 'quantity': 12},
        {'nameZh': '装备B', 'rawText': '装备B=6', 'quantity': 6},
        {'nameZh': '装饰混配100', 'rawText': '混配100=100', 'quantity': 100}]}]}

def test_variants_shared_carton_and_missing_fields(tmp_path):
    out = module.generate(data(), tmp_path / '物流表.xlsx')
    book = load_workbook(out)
    sheet = book['物流表']
    assert [sheet.cell(row, 9).value for row in (2, 3, 4)] == [12, 6, 100]
    assert sheet['B2'].value == 16.05 and sheet['B3'].value is None
    assert 'B2:B4' in sheet.merged_cells
    assert sheet['H2'].value is None and sheet['K2'].value is None
    assert book['待补信息'].max_row == 4 and book['识别依据'].max_row == 4
    assert '申报单价' in book['待补信息']['D2'].value
    assert [c.value for c in sheet[1]] == module.HEADERS
    book.close()

def test_product_image_hs_text_and_formula_injection(tmp_path):
    image = tmp_path / 'product.png'
    Image.new('RGB', (30, 30), 'red').save(image)
    value = data()
    value['cartons'][0]['items'][0].update(imagePath=str(image), hsCode='00123456', nameZh='=HYPERLINK("bad")')
    out = module.generate(value, tmp_path / '物流表.xlsx')
    book = load_workbook(out)
    assert book['物流表']['G2'].data_type == 's'
    assert book['物流表']['K2'].value == '00123456'
    assert len(book['物流表']._images) == 1
    book.close()

@pytest.mark.parametrize('value', [True, 0, -1, 1.5, '12', float('inf')])
def test_invalid_quantities_rejected(tmp_path, value):
    payload = data()
    payload['cartons'][0]['items'][0]['quantity'] = value
    with pytest.raises(ValueError):
        module.generate(payload, tmp_path / 'out.xlsx')

def test_empty_or_duplicate_cartons_rejected(tmp_path):
    with pytest.raises(ValueError): module.generate({'cartons': []}, tmp_path / 'out.xlsx')
    payload = data()
    payload['cartons'][0]['cartonId'] = 'same'
    payload['cartons'] *= 2
    with pytest.raises(ValueError): module.generate(payload, tmp_path / 'out.xlsx')


def test_confirmed_reference_and_consolidated_lines(tmp_path):
    payload = {'cartons': [{'cartonId': '珍奇', 'sourcePhotos': ['carton.jpg'],
        'sourceDocuments': ['confirmed.png'], 'weightKg': 16.05, 'dimensionsCm': [43, 37, 30],
        'items': [{'nameZh': '滑雪圈', 'nameEn': 'Snow tube', 'quantity': 18,
            'declaredUnitPrice': 4, 'material': '塑料', 'hsCode': '3926909090',
            'purpose': '户外', 'brand': '无', 'model': '无',
            'salesUrl': 'https://www.amazon.de/dp/B0HMZNQN2G',
            'sourceItems': [{'name': '装备A', 'quantity': 12}, {'name': '装备B', 'quantity': 6}],
            'consolidationEvidence': '用户确认同一箱内容表合并为滑雪圈'}]}]}
    out = module.generate(payload, tmp_path / 'confirmed.xlsx')
    book = load_workbook(out)
    sheet = book['物流表']
    assert [sheet.cell(2, col).value for col in (2,3,4,5,7,8,9,10,11,12,13,14)] == [16.05,43,37,30,'滑雪圈',4,18,'塑料','3926909090','户外','无','无']
    assert sheet['O2'].hyperlink.target == 'https://www.amazon.de/dp/B0HMZNQN2G'
    assert book['识别依据']['G2'].value == 'confirmed.png'
    assert book['识别依据']['H2'].value == '装备A：12；装备B：6'
    book.close()
    payload['cartons'][0]['items'][0]['quantity'] = 19
    with pytest.raises(ValueError, match='合并数量'):
        module.generate(payload, tmp_path / 'bad.xlsx')
