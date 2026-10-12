"""Read-only collectors used by unified selection. Authentication is always verified."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
import json
import re
import sqlite3
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlencode

import playwright_collector as browser
from category_sources import DOMAINS, normalize_url
from sellersprite_j import PRODUCT_RESEARCH_URL, MARKET_LABELS, _item
from new_releases_history import resolve_database_path

KEYWORD_URL = 'https://www.sellersprite.com/v2/keyword-research'


def amazon_identity(url):
    parsed = urlsplit(str(url))
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('需要 HTTPS Amazon 商品或店铺链接')
    markets = {domain: market for market, domain in DOMAINS.items()}
    market = markets.get((parsed.hostname or '').removeprefix('www.').removeprefix('smile.'))
    if not market:
        raise ValueError('当前选品采集支持 Amazon US/DE；不将其他站点自动改成美德站')
    asin = browser._asin_from_url(url)
    seller = (parse_qs(parsed.query).get('seller') or parse_qs(parsed.query).get('me') or [None])[0]
    if asin:
        kind = 'product'
    elif seller or '/stores/' in parsed.path.lower() or parsed.path.startswith('/stores'):
        kind = 'store'
    elif '/gp/new-releases' in parsed.path:
        kind = 'new_releases'
    else:
        raise ValueError('链接未包含可识别的商品、卖家或品牌店铺身份')
    if seller and not re.fullmatch('[A-Z0-9]{5,32}', seller, re.I):
        raise ValueError('卖家 ID 格式不正确')
    return {'kind': kind, 'marketplace': market, 'asin': asin, 'seller_id': seller, 'url': parsed.geturl()}


@contextmanager
def session(payload, url, *, sellersprite=False):
    with browser._require_playwright()() as runtime:
        context, page, _ = browser._launch_context(runtime, {
            **payload, 'url': url, 'source': 'browser', 'headless': payload.get('headless', True),
            'navigation_timeout_ms': payload.get('navigation_timeout_ms', 30000)})
        try:
            browser._goto(page, url)
            if browser._challenge_visible(page):
                raise browser.BrowserCollectionError('verification_required')
            if sellersprite:
                identity = browser._wait_for_sellersprite_identity(page)
                if identity != 'authenticated':
                    user, password, _ = browser._sellersprite_credentials()
                    if user and password:
                        auth = browser._login_sellersprite_in_page(page, user, password, url, 20, require_asin_query=False)
                        if auth.get('login_status') != 'verified':
                            raise browser.BrowserCollectionError(auth.get('block_reason') or 'login_unverified')
                    else:
                        raise browser.BrowserCollectionError('sellersprite_login_required')
                if browser._wait_for_sellersprite_identity(page) != 'authenticated':
                    raise browser.BrowserCollectionError('sellersprite_login_unverified')
                browser._save_sellersprite_session(context)
            yield page
        finally:
            if sellersprite and browser._sellersprite_auth_state(page) == 'authenticated':
                browser._save_sellersprite_session(context)
            context.close()


def extract_amazon_brand_store(page, market, *, timeout_ms=15000):
    """Read hydrated brand-store tiles; global navigation is not store membership."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    roots = '.stores-page, .stores-container'
    anchors = page.locator(roots).locator('a[href*="/dp/"], a[href*="/gp/product/"]')
    try:
        anchors.first.wait_for(state='attached', timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return []
    rows = anchors.evaluate_all('''elements => elements.map(a => {
        const tile = a.closest('[data-testid="mini-editorial-tile"], [class*="EditorialTile__container"], [data-asin]');
        const img = a.querySelector('img') || tile?.querySelector('img');
        const names = [a.title, a.getAttribute('aria-label'), a.innerText, img?.alt];
        const name = names.map(x => (x || '').trim()).find(x => x && !/^(shop (this product|now)|buy now|learn more|jetzt (kaufen|einkaufen))$/i.test(x));
        return {detail_url:a.href, product_name:name || null, image_url:img?.currentSrc || img?.src || null};
    })''')
    records = {}
    for row in rows:
        try:
            identity = amazon_identity(row['detail_url'])
        except ValueError:
            continue
        if identity['kind'] != 'product' or identity['marketplace'] != market:
            continue
        asin = identity['asin']
        record = records.setdefault(asin, {**row, 'asin': asin, 'marketplace': market})
        for field in ('product_name', 'image_url'):
            if not record.get(field) and row.get(field):
                record[field] = row[field]
    return list(records.values())


def collect_amazon_input(payload):
    identity = amazon_identity(payload['url'])
    market, kind = identity['marketplace'], identity['kind']
    url = identity['url']
    if kind == 'store' and identity['seller_id']:
        url = f"https://www.{DOMAINS[market]}/s?" + urlencode({'me': identity['seller_id']})
    with session({**payload, 'marketplace': market}, url) as page:
        if kind == 'product':
            records = browser.extract_amazon_product(page, {'marketplace': market})
            if not records or not records[0].get('product_name') or records[0].get('asin') != identity['asin']:
                raise browser.BrowserCollectionError('amazon_product_identity_unverified')
        elif kind == 'store':
            if '/stores' in urlsplit(url).path.lower():
                records = extract_amazon_brand_store(page, market)
            else:
                records = browser.extract_amazon_search(page, {'marketplace': market})
            if not records:
                raise browser.BrowserCollectionError('amazon_store_catalog_unavailable')
            records = list({r['asin']: r for r in records if r.get('asin')}.values())
            for row in records:
                row.update({'seller_id': identity['seller_id'], 'store_url': identity['url'],
                            'source_ref': page.url, 'snapshot_date': date.today().isoformat(),
                            'snapshot_complete': False, 'membership': 'seller_catalog' if identity['seller_id'] else 'brand_store'})
        else:
            records = browser.extract_amazon_ranked_list(page, {'marketplace': market})
        directories = page.evaluate('''() => [...document.querySelectorAll(
            '#wayfinding-breadcrumbs_feature_div a[href], #zg_browseRoot a[href], #zg-browse-root a[href], #SalesRank a[href], #detailBulletsWrapper_feature_div a[href*="/bestsellers/"]'
        )].map(a=>({name:a.innerText.trim(),url:a.href})).filter(x=>x.name)''')
        links = page.evaluate('''() => [...document.querySelectorAll('a[href*="/gp/new-releases/"]')]
            .map(a=>({name:a.innerText.trim(),url:a.href})).filter(x=>x.name)''')
        result = {'collection_status': 'partial' if kind == 'store' else 'complete',
                'identity': identity, 'page_title': page.title(), 'source_ref': page.url,
                'records': records[:int(payload.get('limit', 30))], 'directories': directories,
                'new_release_links': links,
                'seller_links': page.locator('#sellerProfileTriggerId[href]').evaluate_all(
                    'es => es.map(e=>({url:e.href,name:e.innerText.trim()}))'),
                'observed_at': browser._now_iso(),
                'coverage_note': '店铺页面为可见样本，不能视为全店完整快照' if kind == 'store' else None,
                'amazon_authentication': 'not_required_for_public_collection'}
    if kind == 'product' and payload.get('resolve_rankings', True):
        result.update(resolve_product_new_releases(payload, market, directories))
    return result


def resolve_product_new_releases(payload, market, directories):
    """Read the site's department links, then verify a product-node ranking page."""
    failures=[]
    if not directories:return {'new_release_links':[], 'ranking_lookup_notes':['商品目录不可读']}
    root=f'https://www.{DOMAINS[market]}/gp/new-releases'
    clean=lambda value: re.sub(r'[^a-z0-9äöüß]+','',str(value).casefold())
    try:
        with session(payload,root) as page:
            departments=page.locator('a[href*="/gp/new-releases/"]').evaluate_all(
                'es=>es.map(e=>({name:e.innerText.trim(),url:e.href}))')
            department=next((x for x in departments if clean(x['name'])==clean(directories[0]['name'])),None)
            if not department:return {'new_release_links':[], 'ranking_lookup_notes':['新品榜首页未找到同名大类，需继续核对目录']}
            base=normalize_url(department['url'],market)
            for directory in list(reversed(directories))[:3]:
                node=(parse_qs(urlsplit(directory['url']).query).get('node') or [None])[0]
                if not node or not node.isdigit():continue
                candidate=base.rstrip('/')+'/'+node
                browser._goto(page,candidate)
                if browser._challenge_visible(page):raise browser.BrowserCollectionError('verification_required')
                heading=' | '.join(page.locator('h1,h2').all_inner_texts())
                actual=normalize_url(page.url,market)
                rows=browser.extract_amazon_ranked_list(page,{'marketplace':market})
                if actual.rstrip('/').endswith('/'+node) and rows and re.search(r'New Releases|Neuerscheinungen',heading,re.I):
                    return {'new_release_links':[{'name':directory['name'],'url':actual,
                        'page_title':page.title(),'verified':True,'source_directory':directory['url'],
                        'relation':'matching_browse_node','sample_count':len(rows)}],
                        'ranking_lookup_notes':failures}
                failures.append(f"{directory['name']}：未核实到同节点新品榜")
    except Exception as exc:
        failures.append(str(exc) if isinstance(exc,(ValueError,browser.BrowserCollectionError)) else type(exc).__name__)
    return {'new_release_links':[], 'ranking_lookup_notes':failures}


def collect_amazon_rankings(payload):
    url = normalize_url(payload['url'], payload['marketplace'])
    result = browser.collect({**payload, 'url': url, 'extractor': 'amazon_ranked_list', 'source': 'amazon_public',
                              'headless': payload.get('headless', True)})
    if not result.get('records') and result.get('collection_status') != 'blocked':
        result.update(collection_status='blocked', block_reason='amazon_ranking_not_verified')
    for row in result.get('records') or []:
        row['category_name'] = payload.get('category')
    return result


def collect_database(payload):
    path = resolve_database_path(payload)
    market = payload['marketplace']
    category = payload.get('db_category')
    asins = list(dict.fromkeys(payload.get('asins') or []))
    if not category and not asins:
        raise ValueError('数据库查询需要核实的类目标识或候选 ASIN，不能把用户整句作为目录')
    end = date.fromisoformat(payload['as_of_date'])
    start = end - timedelta(days=int(payload.get('days', 30)) - 1)
    conditions, params = ['marketplace = ?', 'snapshot_date BETWEEN ? AND ?'], [market, str(start), str(end)]
    if category:
        conditions.append('category = ?'); params.append(category)
    if asins:
        conditions.append('asin IN (' + ','.join('?' for _ in asins) + ')'); params.extend(asins)
    with sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        where = ' AND '.join(conditions)
        count = connection.execute('SELECT COUNT(*) FROM observations WHERE ' + where, params).fetchone()[0]
        rows = [dict(row) for row in connection.execute('SELECT * FROM observations WHERE ' + where +
                 ' ORDER BY snapshot_date DESC, rank LIMIT 5001', params)]
        last = connection.execute('SELECT MAX(snapshot_date) FROM observations WHERE marketplace=?' +
                                  (' AND category=?' if category else ''), [market] + ([category] if category else [])).fetchone()[0]
    records = [{**row, 'source_ref': row.get('source_url'), 'product_name': row.get('title'),
                'observation_date': row.get('snapshot_date'), 'new_release_rank': row.get('rank'),
                'source_type': 'new_releases_db'} for row in rows[:5000]]
    return {'collection_status': 'partial' if count > 5000 else 'complete' if records else 'unavailable',
            'records': records, 'source_metadata': {'db_path': str(path), 'requested_start': str(start),
             'requested_end': str(end), 'latest_scope_snapshot': last, 'matching_observations': count},
            'block_reason': None if records else 'no_database_coverage_in_requested_window'}


def request_fields(request):
    raw = request.post_data or ''
    try:
        body = json.loads(raw)
        if isinstance(body, dict): return body
    except (ValueError, TypeError):
        pass
    return {k: values[-1] for k, values in parse_qs(raw or urlsplit(request.url).query).items()}


def response_matches(response, *, path, expected):
    parsed = urlsplit(response.url)
    if parsed.hostname != 'www.sellersprite.com' or parsed.path != path:
        return False
    values = request_fields(response.request)
    return all((str(values.get(key, '')).lower() == str(value).lower() if isinstance(value, bool)
                else str(values.get(key, '')) == str(value)) for key, value in expected.items())


def verified_query(page, trigger, *, path, expected):
    with page.expect_response(lambda r: response_matches(r, path=path, expected=expected), timeout=25000) as pending:
        trigger()
    response = pending.value
    if response.status != 200:
        raise browser.BrowserCollectionError(f'sellersprite_query_http_{response.status}')
    body = response.json()
    if not isinstance(body, dict) or body.get('code') != 'OK' or body.get('success') is False:
        raise browser.BrowserCollectionError('sellersprite_query_failed_or_permission_required')
    if browser._wait_for_sellersprite_identity(page) != 'authenticated':
        raise browser.BrowserCollectionError('sellersprite_session_lost')
    data = body.get('data')
    if not isinstance(data, dict):
        raise browser.BrowserCollectionError('sellersprite_response_schema_changed')
    return data, request_fields(response.request)


def collect_sellersprite_products(payload):
    market = payload['marketplace']; source = payload['source']; keyword = payload['keyword']
    mode = '研发新品榜' if source == 'sellersprite_new' else '销量飙升榜'
    month = payload.get('history_month')
    with session(payload, PRODUCT_RESEARCH_URL, sellersprite=True) as page:
        market_button = page.get_by_text('选择站点', exact=True).locator('..').get_by_role('button',name=MARKET_LABELS[market])
        market_button.click()
        if month:
            month_button = page.locator('.choose-month button').filter(has_text=month).first
            if not month_button.count():
                return {'collection_status':'unavailable','records':[],'block_reason':'historical_month_not_available'}
            month_button.click()
        mode_button=page.locator('button:visible').filter(has_text=re.compile(r'^\s*'+re.escape(mode)+r'\s*$')).first
        try:
            mode_button.wait_for(state='visible',timeout=5000)
        except Exception:
            return {'collection_status':'unavailable','records':[],
                    'block_reason':'ranking_preset_not_available_for_market',
                    'source_metadata':{'marketplace':market,'mode':mode,'url':page.url}}
        mode_button.click()
        field = _item(page,'包含关键词').locator('input')
        field.fill(keyword)
        match_mode=page.locator('label').filter(has_text='词组匹配').first
        match_mode.click()
        if 'is-checked' not in (match_mode.get_attribute('class') or ''):
            raise browser.BrowserCollectionError('keyword_phrase_match_unverified')
        if field.input_value() != keyword or 'active' not in (market_button.get_attribute('class') or ''):
            raise browser.BrowserCollectionError('product_filter_readback_mismatch')
        if month and 'active' not in (month_button.get_attribute('class') or ''):
            raise browser.BrowserCollectionError('historical_month_readback_mismatch')
        # Product Research sends symbolFlag=true when 'show all variants' is OFF.
        browser._ensure_sellersprite_variants_off(page)
        expected = {'market':market,'keywords':keyword,'selectType':'3','symbolFlag':True,
                    'monthName': 'bsr_sales_monthly_' + month.replace('-','') if month else 'bsr_sales_nearly'}
        if source=='sellersprite_new':expected['productTags']=['NewRelease']
        else:expected.update(minSales='300',minTotalUnitsGrowth='10')
        records=[]; seen=set(); pages=[]; has_more=False; parse_gaps=False; received_count=0
        for index in range(max(1,min(int(payload.get('max_pages',10)),100))):
            browser._ensure_sellersprite_variants_off(page)
            trigger = (lambda: page.get_by_role('button',name='开始筛选').click()) if index==0 else page.locator('.el-pagination .btn-next').first.click
            data,filters=verified_query(page,trigger,path='/v3/api/product-research',expected={**expected,'page':index+1})
            browser._ensure_sellersprite_variants_off(page)
            items=data.get('items')
            if not isinstance(items,list):
                raise browser.BrowserCollectionError('product_response_items_missing')
            requested_ids={str(x.get('asin') or '').upper() for x in items}
            missing_ids = set()
            if items:
                page.wait_for_function("() => ![...document.querySelectorAll('.el-loading-mask')].some(e=>e.offsetWidth || e.offsetHeight)",timeout=15000)
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                rows=browser.extract_sellersprite_table(page,{'marketplace':market})
                rows=[r for r in rows if r.get('asin') in requested_ids]
                if not rows: raise browser.BrowserCollectionError('product_rows_do_not_match_query_response')
                missing_ids = requested_ids - {row.get('asin') for row in rows}
                parse_gaps = parse_gaps or bool(missing_ids)
                raw_by_asin={str(x.get('asin') or '').upper():x for x in items}
                for row in rows:
                    if row['asin'] in seen:continue
                    raw=raw_by_asin[row['asin']]
                    row['category_name']=raw.get('nodeLabelPath') or row.get('category_name')
                    row['sales_growth_percent']=raw.get('totalUnitsGrowth')
                    row['estimated_sales']=raw.get('totalUnits') if raw.get('totalUnits') is not None else row.get('estimated_sales')
                    row['parent_asin']=raw.get('parentAsin') or row.get('parent_asin')
                    row['sales_period']=month or '最近30天'
                    row['filter_keyword']=keyword
                    if month:row['history_month']=month
                    records.append(row);seen.add(row['asin'])
            elif data.get('total') not in (0,'0'):
                raise browser.BrowserCollectionError('empty_product_response_not_verified')
            received_count += len(items)
            has_more=bool(data.get('hasNextPage')) or int(data.get('total') or 0)>received_count
            pages.append({'page':index+1,'records':len(items),'reported_total':data.get('total'), 'unparsed_asins':sorted(missing_ids)})
            if not has_more:break
        return {'collection_status':'partial' if has_more or parse_gaps else 'complete','records':records,
                'coverage_note':'；'.join(note for condition, note in ((has_more, '分页上限截断，返回已验证的商品样本'),
                    (parse_gaps, '部分响应商品未能解析，缺项保留在各页记录')) if condition) or None,
                'source_metadata':{'url':page.url,'marketplace':market,'mode':mode,'filters':filters,
                                   'observed_at':browser._now_iso(),'pages':pages,'show_all_variants':False,
                                   'variants_verified':True,
                                   'scope_method':'标题词组匹配；仍由模型核对目录和用途，不直接作为推荐'}}


def parse_keyword_series(body, market, keyword, source_ref):
    from selection_analysis import month_index, month_label, number
    if not isinstance(body,list): raise browser.BrowserCollectionError('keyword_trend_response_schema_changed')
    series={item.get('key'):item.get('data') for item in body if isinstance(item,dict)}
    times, searches = series.get('time'), series.get('search')
    if not isinstance(times,list) or not isinstance(searches,list) or len(times)!=len(searches):
        raise browser.BrowserCollectionError('keyword_month_axis_unverified')
    records=[]
    for i, value in enumerate(times):
        month=month_index(value)
        if month is None:raise browser.BrowserCollectionError('keyword_month_label_unrecognized')
        row={'marketplace':market,'keyword':keyword,'month':month_label(month),'search_volume':number(searches[i]),
             'source_ref':source_ref,'observed_at':browser._now_iso()}
        for field,key in (('purchase_volume','purchase'),('purchase_rate','rate')):
            values=series.get(key)
            if isinstance(values,list) and len(values)==len(times):row[field]=number(values[i])
        records.append(row)
    return records


def collect_keyword_trends(payload):
    market=payload['marketplace'];keyword=payload['keyword'];station='COM' if market=='US' else 'DE'
    records=[]; product_records=[]; associations=[]; failures=[]
    with session(payload,KEYWORD_URL,sellersprite=True) as page:
        market_name='美国' if market=='US' else '德国'
        page.locator('button').filter(has_text=re.compile(r'^\s*'+market_name+r'\s*$')).first.click()
        page.get_by_placeholder('包含关键词',exact=True).fill(keyword)
        def query_matches(response):
            parsed=urlsplit(response.url);args=parse_qs(parsed.query)
            return (parsed.hostname=='www.sellersprite.com' and parsed.path=='/v2/keyword-research'
                    and args.get('station')==[market] and args.get('includeKeywords')==[keyword]
                    and response.request.resource_type=='document')
        with page.expect_response(query_matches,timeout=25000) as pending:
            page.locator('button').filter(has_text='开始筛选').first.click()
        response=pending.value
        if response.status!=200:raise browser.BrowserCollectionError(f'keyword_query_http_{response.status}')
        page.wait_for_load_state('domcontentloaded')
        if browser._wait_for_sellersprite_identity(page)!='authenticated':
            raise browser.BrowserCollectionError('sellersprite_session_lost')
        args=parse_qs(urlsplit(page.url).query)
        month=args.get('month',[''])[0]
        if not re.fullmatch(r'\d{6}',month):raise browser.BrowserCollectionError('keyword_period_unverified')
        period=f'{month[:4]}-{month[4:]}'
        table=page.locator('table').filter(has=page.locator('th',has_text='月搜索量')).first
        if not table.count():raise browser.BrowserCollectionError('keyword_result_table_missing')
        found=table.locator('tbody tr').filter(has=page.locator('input[data-keyword]'))
        names=[found.nth(i).locator('input[data-keyword]').first.get_attribute('data-keyword') for i in range(found.count())]
        indices=[i for i,name in enumerate(names) if name.casefold()==keyword.casefold()]
        exact=bool(indices)
        if not indices:indices=list(range(min(len(names),3)))
        if not indices:
            body=page.locator('body').inner_text()
            if not re.search(r'暂无数据|没有找到|没有数据',body):raise browser.BrowserCollectionError('keyword_empty_result_unverified')
            return {'collection_status':'complete','records':[],'source_metadata':{'url':page.url,'marketplace':market,'period':period,'keyword':keyword}}
        source_url=page.url
        for index in indices:
            row=found.nth(index);name=names[index]
            product_links=row.locator('.market-popover .popover-item a[href*="/dp/"]').evaluate_all(r'''es=>es.map(e=>({
                detail_url:e.href,product_name:e.querySelector('h4')?.innerText,
                image_url:e.querySelector('.popover-img')?.style.backgroundImage?.match(/url\(["']?(.*?)["']?\)/)?.[1]
            }))''')
            for value in product_links:
                asin=browser._asin_from_url(value['detail_url'])
                if asin:
                    product_records.append({**value,'asin':asin,'marketplace':market,'source_ref':source_url})
                    associations.append({'marketplace':market,'asin':asin,'keyword':name,
                                         'relation':'sellersprite_keyword_related_product','source_ref':source_url})
            control=row.locator('.show-monopoly-trends[pop-type="search"]').first
            path=f'/v2/keyword/history-trend-month/{station}'
            try:
                with page.expect_response(lambda r: response_matches(r,path=path,expected={'q':name}),timeout=20000) as pending:
                    control.click()
                trend=pending.value
                if trend.status!=200:raise browser.BrowserCollectionError(f'keyword_history_http_{trend.status}')
                records.extend(parse_keyword_series(trend.json(),market,name,trend.url))
                if browser._wait_for_sellersprite_identity(page)!='authenticated':
                    raise browser.BrowserCollectionError('sellersprite_session_lost')
            except Exception as exc:
                # Retain only the verified current-month row when a history permission/query fails.
                cells=row.locator('td').all_inner_texts()
                volume=browser._parse_integer(cells[5].splitlines()[0]) if len(cells)>5 else None
                if volume is not None:
                    records.append({'marketplace':market,'keyword':name,'month':period,'search_volume':volume,'source_ref':source_url})
                failures.append({'keyword':name,'reason':str(exc) if isinstance(exc,browser.BrowserCollectionError) else type(exc).__name__})
            close=page.locator('.modal:visible [data-dismiss="modal"], .modal:visible button.close').first
            if close.count():close.click()
        return {'collection_status':'partial' if failures or not exact else 'complete','records':records,
                'product_records':list({r['asin']:r for r in product_records}.values()),'associations':associations,
                'coverage_note':'仅查询精确种子词的历史，相关词未穷尽' if exact else '关键词结果取前三个方向，未穷尽全部相关词',
                'failures':failures,'source_metadata':{'url':source_url,'marketplace':market,'period':period,
                 'seed_keyword':keyword,'selected_keywords':[names[i] for i in indices],'history_failures':failures}}
