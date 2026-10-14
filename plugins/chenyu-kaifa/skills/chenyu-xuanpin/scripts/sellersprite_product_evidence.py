"""Read the visible monthly-sales table in the existing shared SellerSprite browser."""
from datetime import date
import json
import re
from pathlib import Path
from urllib.parse import urlencode

import playwright_collector as browser
from sellersprite_session import launch_context, ensure_login
from product_evidence import history_is_sufficient

LOOKUP_URL = 'https://www.sellersprite.com/v3/competitor-lookup'


def parse_monthly_table(table, *, marketplace, asin, source_ref, as_of_date=None, sales_scope="parent"):
    """Keep full-month values and lower bounds; never coerce absent cells to zero."""
    if sales_scope not in ("parent", "child"):
        raise ValueError("invalid_sales_scope")
    cutoff = date.fromisoformat(as_of_date or date.today().isoformat()).strftime('%Y-%m')
    headers, rows, labels = table['headers'], table['rows'], table['labels']
    sales_rows = [i for i, label in enumerate(labels) if label.strip() in ('月销量', 'Monthly Sales')]
    if len(sales_rows) != 1 or sales_rows[0] >= len(rows):
        raise ValueError('monthly_sales_row_unverified')
    values = rows[sales_rows[0]]
    points, missing, seen = [], [], set()
    for i, label in enumerate(headers):
        month = str(label).strip()
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
            continue
        if month in seen:
            raise ValueError('duplicate_history_month')
        seen.add(month)
        if month >= cutoff:
            continue
        value = str(values[i]).strip().replace(',', '') if i < len(values) else ''
        upper = re.fullmatch(r'[<＜]\s*(\d+(?:\.\d+)?)([KM]?)', value, re.I)
        numeric = re.fullmatch(r'(\d+(?:\.\d+)?)([KM]?)(\+?)', value, re.I)
        if upper:
            numeric = re.fullmatch(r'(\d+(?:\.\d+)?)([KM]?)(\+?)', upper[1] + upper[2], re.I)
        if not numeric:
            missing.append(month)
            continue
        points.append({'marketplace': marketplace, 'asin': asin, 'month': month,
                       'estimated_sales': float(numeric[1]) * {'': 1, 'K': 1000, 'M': 1000000}[numeric[2].upper()],
                       'sales_scope': sales_scope, 'sales_display': str(values[i]).strip(),
                       'value_kind': 'upper_bound' if upper else 'lower_bound' if numeric[3] else 'estimate',
                       **({'bound_exclusive': True} if upper else {}),
                       'period_complete': True, 'source_ref': source_ref})
    return sorted(points, key=lambda p: p['month']), missing


TABLE_JS = '''root => {
 const cells = row => Array.from(row?.cells || []).map(c => c.innerText.trim());
 const head = root.querySelector('.el-table__header-wrapper table');
 const body = root.querySelector('.el-table__body-wrapper table');
 const fixed = root.querySelector('.el-table__fixed-body-wrapper table');
 return {headers: cells(head?.rows[0]),
         rows: Array.from(body?.rows || []).map(cells),
         labels: Array.from(fixed?.rows || body?.rows || []).map(r => cells(r)[0] || '')};
}'''


def read_series(page, row, market, asin, series_asin, sales_scope, options, source):
    tab_name = 'sell' if sales_scope == 'parent' else 'amzunit'
    if sales_scope == 'parent':
        row.locator('.icon-historical-trend').click()
    else:
        header = page.locator('.el-table__header-wrapper th').filter(has_text=re.compile('子体销量')).last
        columns = [c for c in (header.get_attribute('class') or '').split()
                   if re.fullmatch(r'el-table_\d+_column_\d+', c)]
        if len(columns) != 1:
            raise ValueError('child_sales_column_unverified')
        cell = row.locator('td.' + columns[0] + ' .border-bt').first
        if not cell.count():
            return {'collection_status': 'unavailable', 'history': [], 'block_reason': 'child_sales_entry_unavailable'}
        cell.click()
    dialog = page.locator('[role="dialog"]:visible').last
    try:
        dialog.wait_for(state='visible', timeout=15000)
        tab = dialog.locator(f'#tab-{tab_name}')
        if tab.get_attribute('aria-selected') != 'true':
            tab.click()
        pane = dialog.locator(f'#pane-{tab_name}')
        pane.wait_for(state='visible', timeout=15000)
        # Product identity is populated with the trend response. An empty
        # skeleton or a prior ASIN must never be treated as this product's data.
        pane.get_by_text(asin, exact=True).first.wait_for(state='visible', timeout=15000)
        page.wait_for_function("""selector => {
          const p = document.querySelector(selector);
          if (!p) return false;
          const busy = Array.from(p.querySelectorAll('.el-loading-mask')).some(e => e.getClientRects().length);
          return !busy && (/\\d{4}-\\d{2}/.test(p.innerText) && p.querySelector('.el-table__body-wrapper tr')
            || /暂无数据|No Data/.test(p.innerText));
        }""", arg=f'[role="dialog"] #pane-{tab_name}', timeout=15000)
        raw = pane.locator('.el-table').first.evaluate(TABLE_JS)
        if not raw['rows']:
            return {'collection_status': 'unavailable', 'history': [],
                    'block_reason': 'visible_monthly_table_empty', 'raw_table': raw}
        points, gaps = parse_monthly_table(raw, marketplace=market, asin=series_asin,
            source_ref=source, as_of_date=options.get('as_of_date'), sales_scope=sales_scope)
        return {'history': points, 'missing_months': gaps, 'raw_table': raw,
                'collection_status': 'complete' if history_is_sufficient(points) and not gaps else 'partial',
                'sales_scope': sales_scope,
                'coverage_verified': history_is_sufficient(points) and not gaps}
    finally:
        close = dialog.locator('.close-wrap .close, .el-dialog__headerbtn')
        if not close.count():
            raise ValueError('history_dialog_close_unavailable')
        close.first.click()
        dialog.wait_for(state='hidden', timeout=5000)


def read_history(page, market, asin, options):
    browser._select_sellersprite_market(page, market)
    def trigger():
        browser._ensure_sellersprite_variants_off(page)
        browser._wait_for_sellersprite_asin_input(page, 5000).fill(asin)
        page.get_by_role('button', name=re.compile(r'立即查询|search', re.I)).first.click()
    records, _, reason = browser._wait_sellersprite_query(
        page, options, market, [asin], trigger, 15000, 200)
    matched = [r for r in records if r.get('asin') == asin and r.get('marketplace') == market]
    if reason != 'matched' or len(matched) != 1:
        raise ValueError(reason or 'history_product_identity_unverified')
    row = page.locator('tr').filter(has_text=re.compile(r'ASIN:\s*' + re.escape(asin) + r'\b')).first
    parent = re.search(r'父ASIN\s*:\s*([A-Z0-9]{10})\b', row.inner_text())
    if not parent:
        raise ValueError('history_parent_identity_unverified')
    source = LOOKUP_URL + '?' + urlencode({'market': market, 'asins': json.dumps([asin])})
    series = {}
    for sales_scope, series_asin in [('parent', parent.group(1)), ('child', asin)]:
        if options.get('sales_scope', 'both') not in ('both', sales_scope):
            continue
        try:
            series[sales_scope] = read_series(page, row, market, asin, series_asin, sales_scope, options, source)
        except Exception as exc:
            series[sales_scope] = {'collection_status': 'blocked', 'history': [],
                'block_reason': str(exc) if type(exc) is ValueError else type(exc).__name__}
    preferred = next((series[key] for key in ('parent', 'child') if series.get(key, {}).get('history')), {})
    return {'marketplace': market, 'asin': asin, 'parent_asin': parent.group(1),
            'collection_status': 'complete' if all(v['collection_status'] == 'complete' for v in series.values()) else 'partial',
            'history': preferred.get('history', []), 'sales_scope': preferred.get('sales_scope'),
            'series': series, 'source_ref': source,
            'collected_as_of': options.get('as_of_date') or date.today().isoformat(),
            'coverage_note': '仅已完成月份；父子体分开；保留销量上下界；不足12个连续月须补查时间范围、父体与同族子体，不作为完整生命周期交付'}


def collect_product_evidence(payload):
    market = payload.get('marketplace')
    asins = payload.get('asins')
    if market not in ('US', 'DE') or not isinstance(asins, list) or not 1 <= len(asins) <= 50:
        raise ValueError('历史证据采集需要US/DE站点及1–50个ASIN')
    if any(not isinstance(a, str) or not re.fullmatch(r'[A-Z0-9]{10}', a) for a in asins):
        raise ValueError('ASIN格式不正确')
    sales_scope = payload.get('sales_scope', 'both')
    if sales_scope not in ('both', 'parent', 'child'):
        raise ValueError('sales_scope必须为both/parent/child')
    if payload.get('as_of_date'):
        date.fromisoformat(payload['as_of_date'])
    options = {**(payload.get('browser') or {}), 'as_of_date': payload.get('as_of_date'), 'sales_scope': sales_scope}
    outcomes = []
    user, password, _ = browser._sellersprite_credentials()
    with browser._require_playwright()() as runtime:
        context, page, _ = launch_context(runtime, options)
        try:
            auth = ensure_login(page, user, password, destination=LOOKUP_URL)
            if auth.get('login_status') != 'verified':
                return {'ok': False, 'status': 'AWAITING_ENRICHMENT',
                        'block_reason': auth.get('block_reason') or 'sellersprite_login_unverified', 'products': []}
            for asin in dict.fromkeys(asins):
                try:
                    outcomes.append(read_history(page, market, asin, options))
                except Exception as exc:
                    # Do not serialize browser exceptions containing session URLs or credentials.
                    reason = str(exc) if type(exc) is ValueError and re.fullmatch(r'[a-z_]+', str(exc)) else type(exc).__name__
                    outcomes.append({'marketplace': market, 'asin': asin, 'collection_status': 'blocked',
                                     'block_reason': reason, 'history': []})
                    if browser._sellersprite_auth_state(page) != 'authenticated' or browser._challenge_visible(page):
                        break
                    browser._goto(page, LOOKUP_URL)
        finally:
            context.close()
    result = {'ok': True, 'status': 'COMPLETE' if all(p['collection_status'] == 'complete' for p in outcomes) else 'PARTIAL',
              'products': outcomes,
              'next_required_action': '先核对连续12个月覆盖；短历史继续检查全部时间范围、父体及同族子体，保留各自口径与实际访问阻塞；不得把有限观察作为生命周期交付。'}
    if payload.get('run_dir'):
        folder = Path(payload['run_dir']).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        for product in outcomes:
            path = folder / f"product-history-{market}-{product['asin']}.json"
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(product, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
        result['run_dir'] = str(folder)
    return result
