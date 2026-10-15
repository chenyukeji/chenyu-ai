import sys
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'))
from selection_collectors import ensure_product_list_view
from playwright_collector import BrowserCollectionError

@pytest.fixture(scope='module')
def browser():
 with sync_playwright() as p:
  b=p.chromium.launch(headless=True,args=['--no-sandbox'])
  yield b
  b.close()

@pytest.mark.parametrize('hidden', [False, True])
def test_image_view_switches_to_list_even_before_toolbar_visible(browser, hidden):
 page=browser.new_page()
 try:
  page.set_content('<div style="'+('display:none' if hidden else '')+'"><button class="el-button is-plain" onclick="this.classList.remove(\'is-plain\');window.listMode=true">列表</button></div>')
  ensure_product_list_view(page)
  assert page.evaluate('window.listMode') is True
  page.evaluate('window.listMode=false')
  ensure_product_list_view(page)
  assert page.evaluate('window.listMode') is False
 finally:page.close()

def test_missing_control_is_reported_instead_of_empty_data(browser):
 page=browser.new_page()
 try:
  with pytest.raises(BrowserCollectionError,match='product_list_view_control_unavailable'):
   ensure_product_list_view(page)
 finally:page.close()

def test_common_parser_reads_asin_lookup_after_switching_from_cards(browser):
 from playwright_collector import extract_sellersprite_table
 page=browser.new_page()
 try:
  page.set_content('''<button class="el-button is-plain" onclick="this.classList.remove('is-plain');document.querySelector('table').style.display=''">列表</button>
  <table style="display:none"><thead><tr><th>ASIN</th><th>产品名称</th></tr></thead>
  <tbody><tr><td>B0C6FCKQML</td><td>DREO Space Heater</td></tr></tbody></table>''')
  rows=extract_sellersprite_table(page,{'marketplace':'US'})
  assert len(rows)==1 and rows[0]['asin']=='B0C6FCKQML'
 finally:page.close()


@pytest.mark.parametrize('display,expected', [('-', None), ('—', None), ('0', 0), ('25', 25)])
def test_missing_rating_counts_are_not_zero(display, expected):
 from playwright_collector import _parse_sellersprite_combined_fields, _normalise_date
 record = {}
 _parse_sellersprite_combined_fields(record, ['评分数 月新增'], [display + '\n-'], [])
 assert record['review_count'] == expected
 assert _normalise_date('--') is None
 assert _normalise_date('2026-09-24\n21天') == '2026-09-24'


@pytest.mark.parametrize('detail_asin', ['B0779RDWVZ', 'B099999999', ''])
def test_expanded_category_is_bound_to_its_product(browser, detail_asin):
 from playwright_collector import extract_sellersprite_table, SELLERSPRITE_COMPETITOR_HEADERS
 from html import escape
 page = browser.new_page()
 try:
  headers = SELLERSPRITE_COMPETITOR_HEADERS
  cells = [''] * len(headers)
  cells[headers.index('产品信息')] = 'Winter Gloves\nASIN: B0779RDWVZ\n父ASIN: B0779RL486'
  cells[headers.index('评分数 月新增')] = '-\n-'
  cells[headers.index('上架时间')] = '--'
  page.set_content('<table><thead><tr>' + ''.join('<th>'+escape(h)+'</th>' for h in headers) +
   '</tr></thead><tbody><tr>' + ''.join('<td>'+escape(c).replace('\n','<br>')+'</td>' for c in cells) +
   '</tr><tr><td class="el-table__expanded-cell" colspan="17"><label class="table-check">'
   '<input type="checkbox" value="'+detail_asin+'"></label><div class="product-type">'
   '<a class="type" href="https://www.sellersprite.com/v3/product-research?nodeIdPaths=1">Clothing</a>'
   '<a class="type" href="https://www.sellersprite.com/v3/product-research?nodeIdPaths=2">Gloves</a>'
   '</div><div class="product-rank">#15 in Gloves</div><div class="product-info">'
   '<span class="info-item">商品重量: 0.3 pounds</span></div></td></tr></tbody></table>')
  records = extract_sellersprite_table(page, {'marketplace':'US'})
  assert len(records) == 1
  record = records[0]
  assert record['review_count'] is None and record['source_available_date'] is None
  if detail_asin == 'B0779RDWVZ':
   assert record['category_name'] == 'Clothing > Gloves'
   assert record['category_path'] == ['Clothing','Gloves']
   assert len(record['category_links']) == 2
   assert record['product_info'] == ['商品重量: 0.3 pounds']
   assert record['small_bsr'] == '#15 in Gloves'
  else:
   assert not record.get('category_name')
 finally:
  page.close()
