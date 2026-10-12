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
