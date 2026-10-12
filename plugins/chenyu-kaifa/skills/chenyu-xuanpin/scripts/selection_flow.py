"""Unified, resumable selection orchestration for one skill and multiple sources."""
from __future__ import annotations

from datetime import date
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re

from category_sources import normalize_url
from selection_analysis import analyze_keywords, merge_products, summarize_products, balanced_shortlist, SOURCE_LABELS
import selection_collectors as collectors
from strategy_h import target_months

SOURCES = ('amazon_new_releases', 'sellersprite_new', 'sellersprite_surge',
           'sellersprite_history', 'keyword_trends', 'new_releases_db')
VERSION = 'selection-v1'


def query_id(spec):
    return hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def plan_selection(payload):
    request = str(payload.get('request') or '').strip()
    scope = dict(payload.get('scope') or {})
    if set(scope)-{'input_urls','marketplaces','sources','categories','following_months','shortlist_limit','filters','exclusions'}:
        raise ValueError('scope 包含不支持的字段')
    filters=scope.get('filters') or {}
    if set(filters)-{'price_min','price_max','review_max','sales_min','fulfillment'}:
        raise ValueError('filters 包含不支持的筛选条件')
    for key,value in filters.items():
        if key=='fulfillment':
            if value not in ('FBM','FBA','AMZ'): raise ValueError('配送方式仅支持 FBM/FBA/AMZ')
        elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('数值筛选条件须为非负数字')
    links = scope.get('input_urls') or re.findall(r'https://[^\s<>"，。]+', request)
    if not isinstance(links,list) or any(not isinstance(x,str) for x in links):
        raise ValueError('input_urls 必须为链接数组')
    identities = [collectors.amazon_identity(url.rstrip(').）')) for url in links]
    markets = scope.get('marketplaces') or list(dict.fromkeys(x['marketplace'] for x in identities))
    if not markets:
        mentioned = [m for m, words in {'US': ('美国', '美站'), 'DE': ('德国', '德站')}.items()
                     if any(word in request for word in words)]
        markets = mentioned or ['US', 'DE']
    if not isinstance(markets, list) or any(m not in ('US', 'DE') for m in markets):
        raise ValueError('scope.marketplaces 仅支持 US/DE')
    markets = list(dict.fromkeys(markets))
    if any(x['marketplace'] not in markets for x in identities):
        raise ValueError('链接站点不在目标站点中；请先明确跨站目录映射')
    sources = scope.get('sources', list(SOURCES))
    if not isinstance(sources, list) or not sources or set(sources) - set(SOURCES):
        raise ValueError('scope.sources 包含不支持的数据来源')
    as_of = date.fromisoformat(payload.get('as_of_date') or str(date.today())).isoformat()
    months = target_months(as_of, scope.get('following_months', 2))
    categories = scope.get('categories') or []
    if not isinstance(categories, list):
        raise ValueError('scope.categories 必须为数组')
    queries, missing = [], []
    for identity in identities:
        queries.append({'source': 'amazon_input', **identity})
    if not categories:
        missing.append('请模型根据用户类目或链接事实，填入 scope.categories 和各站点关键词/已核实榜单入口')
    for category in categories:
        if not isinstance(category,dict): raise ValueError('类目必须为对象')
        name = category.get('name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('类目必须包含非空 name')
        for market in markets:
            terms = (category.get('keywords') or {}).get(market, [])
            if isinstance(terms, str): terms = [terms]
            if not isinstance(terms, list) or any(not isinstance(x, str) or not x.strip() or len(x)>100 for x in terms):
                raise ValueError('每站点 keywords 必须是非空短词数组')
            terms = list(dict.fromkeys(x.strip() for x in terms))
            if any(x in sources for x in ('sellersprite_new','sellersprite_surge','sellersprite_history','keyword_trends')) and not terms:
                missing.append(f'{name}/{market}：缺少已核对的本地语言关键词')
            for source in sources:
                base = {'source': source, 'marketplace': market, 'category': name, 'as_of_date': as_of}
                if source == 'amazon_new_releases':
                    urls = (category.get('amazon_new_releases') or {}).get(market) or []
                    if isinstance(urls, str): urls = [urls]
                    if not urls:
                        queries.append({**base, 'unavailable': '尚未找到并核实对应目录的新品榜入口'})
                    for url in urls:
                        queries.append({**base, 'url': normalize_url(url, market)})
                elif source == 'new_releases_db':
                    mapped = (category.get('db_categories') or {}).get(market) or []
                    if isinstance(mapped, str): mapped = [mapped]
                    for db_category in mapped or [None]:
                        queries.append({**base, 'db_category': db_category})
                else:
                    for term in terms:
                        for month in months if source == 'sellersprite_history' else [None]:
                            spec = {**base, 'keyword': term}
                            if month: spec['history_month'] = month
                            queries.append(spec)
    limit = scope.get('shortlist_limit', 20)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('shortlist_limit 必须为 1–100')
    unique = {query_id(q): q for q in queries}
    if len(unique) > 120:
        raise ValueError('查询任务超过 120 项，请按类目分批调查')
    return {'version': VERSION, 'request': request, 'scope': scope, 'as_of_date': as_of,
            'marketplaces': markets, 'historical_months': months, 'shortlist_limit': limit,
            'queries': [{'id': key, **value} for key, value in unique.items()], 'blocking_items': missing}


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def collect_query(query, payload, known_products):
    if query.get('unavailable'):
        return {'collection_status': 'unavailable', 'records': [], 'block_reason': query['unavailable']}
    options = {**(payload.get('browser') or {}), **query}
    source = query['source']
    if source == 'amazon_input': return collectors.collect_amazon_input(options)
    if source == 'amazon_new_releases': return collectors.collect_amazon_rankings(options)
    if source in ('sellersprite_new','sellersprite_surge','sellersprite_history'):
        return collectors.collect_sellersprite_products(options)
    if source == 'keyword_trends': return collectors.collect_keyword_trends(options)
    if source == 'new_releases_db':
        options['db_path'] = payload.get('db_path') or os.environ.get('CHENYU_NEW_RELEASES_DB')
        if not options.get('db_category'):
            options['asins'] = [x['asin'] for x in known_products if x['marketplace'] == query['marketplace']]
        return collectors.collect_database(options)
    raise ValueError('unknown selection source')



def original_style_rows(rows, report):
    """Put combined evidence in the familiar 15-column selection table."""
    products = {(p['marketplace'], p['asin']): p for p in report['products']}
    result = []
    for row in rows:
        current = (products.get((row['站点'], row['ASIN'])) or {}).get('current') or {}
        analysis = str(row.get('分析') or '').strip()
        summary = re.split(r'[。；;]', analysis, maxsplit=1)[0].strip()
        if not re.search(r'[\u3400-\u9fff]', summary):
            summary = ''
        category = str(row.get('所在品类') or '')
        if '圣诞' in category or 'christmas' in category.casefold():
            lifecycle = '10–12月（圣诞季，需复核）'
        elif '万圣' in category or 'halloween' in category.casefold():
            lifecycle = '8–10月（万圣节季，需复核）'
        else:
            lifecycle = '需结合历史趋势复核'
        priority = row.get('优先级') or ''
        conclusion = {'优先研究': '🟢 优先研究', '继续观察': '🟡 继续观察',
                      '低优先级': '🔴 低优先级', '待补数据': '🟡 待补数据',
                      '待核对相关性': '🟡 待核对相关性'}.get(priority, priority)
        reasons = [analysis]
        for label, key in (('命中来源', '命中来源'), ('历史命中月份', '历史命中月份'),
                           ('关联关键词', '关联关键词'), ('证据缺项', '证据缺项')):
            if row.get(key):
                reasons.append(f'{label}：{row[key]}')
        result.append({'站点': row['站点'], '上架日期': row.get('上架日期'),
                       'Review数量': row.get('评论量'), '售价（当地币种）': row.get('售价'),
                       '大品类排名': current.get('bsr'), '所在品类': row.get('所在品类'),
                       '预估月销量': row.get('当前预估月销量'), '产品优点&特征': summary,
                       '缺点': '', '生命周期': lifecycle, 'ASIN': row['ASIN'],
                       '亚马逊产品链接': row.get('亚马逊产品链接'), '图片': row.get('图片'),
                       '结论': conclusion, '理由': '\n'.join(x for x in reasons if x)})
    return result


def export_workbook(path, rows, report, image_loader=None):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.drawing.image import Image
    from openpyxl.utils import get_column_letter
    from discovery_workbook import HEADERS, _download_image
    loader = image_loader or _download_image
    wb = Workbook(); wb.remove(wb.active)
    main_rows = original_style_rows(rows, report)
    history = [{'站点': p['marketplace'], 'ASIN': p['asin'], '月份': h['history_month'],
                '历史月销量': h.get('estimated_sales'), '历史环比增长率': h.get('sales_growth_percent'),
                '来源': h.get('source_ref')} for p in report['products'] for h in p['historical']]
    keywords = [{'站点': d['marketplace'], '关键词': d['keyword'], '最新完整月份': d['latest_month'],
                 '搜索量': d['search_volume'], '环比%': d['mom_percent'], '同比%': d['yoy_percent'],
                 '绝对变化': d['absolute_change'], '完整月滞后数': d['data_lag_months'],
                 '说明': '；'.join(d['evidence'])} for d in report['keywords']['directions']]
    keyword_history = [{'站点': d['marketplace'], '关键词': d['keyword'], '月份': r['month'],
                        '搜索量': r['search_volume'], '来源': r['source_ref']}
                       for d in report['keywords']['directions'] for r in d['history']]
    coverage = [{'来源': SOURCE_LABELS.get(r['query']['source'],r['query']['source']), '站点': r['query'].get('marketplace'),
                 '类目': r['query'].get('category'), '关键词': r['query'].get('keyword'),
                 '月份': r['query'].get('history_month'), '状态': r.get('collection_status'),
                 '条数': len(r.get('records') or []), '说明': r.get('block_reason') or r.get('coverage_note'),
                 '统计上下文': json.dumps(r.get('source_metadata') or {}, ensure_ascii=False)} for r in report['results']]
    image_cache = {}; errors = []
    # Reuse images from the prior workbook by marketplace/ASIN on a resumed task.
    previous_images = {}
    if path.exists():
        previous = load_workbook(path)
        previous_title = next((name for name in ('开品结果', '选品结果') if name in previous.sheetnames), None)
        if previous_title:
            sheet = previous[previous_title]; headers = [c.value for c in sheet[1]]
            if '站点' in headers and 'ASIN' in headers:
                for image in sheet._images:
                    n = image.anchor._from.row + 1
                    previous_images[(sheet.cell(n, headers.index('站点')+1).value,
                                     sheet.cell(n, headers.index('ASIN')+1).value)] = image._data()
        previous.close()
    sheets = [('开品结果', main_rows), ('关键词趋势', keywords), ('关键词月度明细', keyword_history),
              ('季节性明细', history), ('来源与覆盖', coverage)]
    border = Border(*(Side(style='thin', color='666666') for _ in range(4)))
    main_widths = dict(zip(HEADERS, [8, 13, 11, 15, 12, 16, 13, 28, 27, 24, 14, 31, 22, 15, 65]))
    for title, values in sheets:
        ws = wb.create_sheet(title)
        headers = HEADERS if title == '开品结果' else list(dict.fromkeys(k for row in values for k in row)) or ['说明']
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(name='Microsoft YaHei', size=11, bold=True)
            cell.fill = PatternFill('solid', fgColor='C6E0B4')
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = border
        ws.row_dimensions[1].height = 32
        for row in values:
            ws.append([None if key=='图片' else row.get(key) for key in headers])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value, str): cell.data_type = 's'
                cell.font = Font(name='Microsoft YaHei', size=10)
                cell.alignment = Alignment(horizontal='left' if title == '开品结果' and cell.column == 15 else 'center', vertical='center', wrap_text=True)
                cell.border = border
            if title == '开品结果':
                ws.row_dimensions[ws.max_row].height = 110
                conclusion_cell = ws.cell(ws.max_row, headers.index('结论') + 1)
                conclusion = str(conclusion_cell.value or '')
                color = '33A36B' if '优先研究' in conclusion else 'F4CCCC' if '低优先级' in conclusion else 'FFD966'
                conclusion_cell.fill = PatternFill('solid', fgColor=color)
                conclusion_cell.font = Font(name='Microsoft YaHei', size=10, bold=True,
                                            color='FFFFFF' if color == '33A36B' else '000000')
            if '图片' in headers and row.get('图片'):
                try:
                    url = row['图片']; identity = (row.get('站点'), row.get('ASIN'))
                    if identity in previous_images: image_cache[url] = previous_images[identity]
                    if url not in image_cache: image_cache[url] = loader(url)[0]
                    img = Image(BytesIO(image_cache[url])); ratio = min(110/img.width,85/img.height)
                    img.width *= ratio; img.height *= ratio
                    ws.add_image(img, f'{get_column_letter(headers.index("图片")+1)}{ws.max_row}')
                    if title != '开品结果': ws.row_dimensions[ws.max_row].height = 68
                except Exception:
                    errors.append({'marketplace': row.get('站点'), 'asin': row.get('ASIN'), 'reason': 'image_embedding_failed'})
                    ws.cell(ws.max_row,headers.index('图片')+1,'图片未取得')
            if '亚马逊产品链接' in headers and row.get('亚马逊产品链接'):
                ws.cell(ws.max_row,headers.index('亚马逊产品链接')+1).hyperlink = row['亚马逊产品链接']
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for i, header in enumerate(headers,1):
            ws.column_dimensions[get_column_letter(i)].width = (main_widths[header] if title == '开品结果'
                else 42 if header in ('分析','说明','统计上下文','产品名称') else 22)
    temporary = path.with_suffix('.tmp.xlsx'); wb.save(temporary); temporary.replace(path)
    return {'path': str(path), 'row_count': len(rows), 'image_failures': errors}


def run_selection(payload):
    raw_dir = payload.get('run_dir')
    if not raw_dir: raise ValueError('run_selection 需要按输出目录规范传入 run_dir')
    folder = Path(raw_dir).expanduser().resolve(); folder.mkdir(parents=True,exist_ok=True)
    plan_path = folder/'selection-plan.json'
    if plan_path.exists() and not payload.get('request') and not payload.get('scope'):
        plan=json.loads(plan_path.read_text())
        if plan.get('version')!=VERSION: raise ValueError('不能续跑不兼容的选品目录')
    else:
        plan=plan_selection(payload); write_json(plan_path,plan)
    settings_path=folder/'selection-settings.json'
    settings=json.loads(settings_path.read_text()) if settings_path.exists() else {}
    for key in ('browser','db_path','enrich','associations'):
        if key in payload: settings[key]=payload[key]
    browser_options=settings.get('browser') or {}
    if set(browser_options)-{'profile_dir','headless','max_pages','limit','navigation_timeout_ms','query_timeout_ms','query_delay_ms'}:
        raise ValueError('browser 包含不支持的字段；账号密码仅通过环境变量传入')
    write_json(settings_path,settings)
    payload={**settings,**payload}
    options = payload.get('browser') or {}
    budget = payload.get('max_queries', 20)
    if type(budget) is not int or not 1 <= budget <= 120: raise ValueError('max_queries 必须为 1–120')
    results=[]; pending=[]; executed=0; auth_block=None
    for query in plan['queries']:
        digest=query_id({'query':query,'browser':{k:v for k,v in options.items() if k not in ('profile_dir','headless')},
                         'db_path':payload.get('db_path') or os.environ.get('CHENYU_NEW_RELEASES_DB')})
        cache=folder/f'source-{digest}.json'
        result=json.loads(cache.read_text()) if cache.exists() and not payload.get('refresh') else None
        if result and result.get('collection_status') in ('blocked','unavailable','pending'):
            result=None
        if result is None:
            if executed>=budget:
                pending.append(query['id']); continue
            try:
                if auth_block and query['source'] in ('sellersprite_new','sellersprite_surge','sellersprite_history','keyword_trends'):
                    result={'collection_status':'blocked','block_reason':auth_block,'records':[]}
                else:
                    result=collect_query(query,payload,merge_products(results)); executed+=1
            except Exception as exc:
                # Library exceptions can include URLs or account-page text. Keep only safe class names.
                reason=str(exc) if isinstance(exc,(ValueError,collectors.browser.BrowserCollectionError)) else type(exc).__name__
                result={'collection_status':'blocked','block_reason':reason[:240],'records':[]}; executed+=1
            reason=result.get('block_reason') or ''
            if query['source'] in ('sellersprite_new','sellersprite_surge','sellersprite_history','keyword_trends') and any(
                term in reason for term in ('login','session_lost','verification_required','authentication','permission_required')):
                auth_block=reason
            result['query']=query; write_json(cache,result)
        results.append(result)
        if result.get('product_records'):
            results.append({'query':{'id':query['id']+'-products','source':'keyword_products','marketplace':query.get('marketplace')},
                            'records':result['product_records'],'collection_status':'complete',
                            'coverage_note':'关键词页面实际展示的关联商品样本，相关性待模型核对'})
    associations=[a for result in results for a in result.get('associations',[])]+(payload.get('associations') or [])
    products=merge_products(results,associations=associations)
    shortlisted=balanced_shortlist(products,plan['shortlist_limit'])
    if payload.get('enrich',True) and shortlisted and not pending and not plan['blocking_items'] and not auth_block:
        for market in plan['marketplaces']:
            asins=[p['asin'] for p in shortlisted if p['marketplace']==market and
                   any(p['current'].get(f) is None for f in ('price','estimated_sales','source_available_date','review_count'))]
            if not asins: continue
            spec={'source':'sellersprite_enrichment','marketplace':market,'asins':asins}
            cache=folder/f'enrichment-{query_id(spec)}.json'
            result=json.loads(cache.read_text()) if cache.exists() and not payload.get('refresh') else None
            if not result or result.get('collection_status')!='complete':
                try: result=collectors.browser.collect_sellersprite_by_asin({**options,'marketplace':market,'asins':asins,'headless':True})
                except Exception as exc: result={'collection_status':'blocked','block_reason':type(exc).__name__,'records':[]}
                result['query']={'id':query_id(spec),**spec};write_json(cache,result)
            results.append(result)
        products=merge_products(results,associations=associations)
        identities={(p['marketplace'],p['asin']) for p in shortlisted}
        shortlisted=[p for p in products if (p['marketplace'],p['asin']) in identities]
    for item in shortlisted:
        checks=[]
        for key, value in (plan['scope'].get('filters') or {}).items():
            field={'price_min':'price','price_max':'price','review_max':'review_count','sales_min':'estimated_sales','fulfillment':'fulfillment'}[key]
            actual=item['current'].get(field)
            if actual is None:checks.append({'condition':key,'status':'missing'})
            else:
                passed=actual==value if key=='fulfillment' else actual>=value if key.endswith('_min') else actual<=value
                checks.append({'condition':key,'status':'pass' if passed else 'fail','actual':actual,'expected':value})
        item['filter_checks']=checks
    keyword_records=[r for result in results if result['query']['source']=='keyword_trends' for r in result.get('records',[])]
    report={'version':VERSION,'plan':plan,'results':results,'products':products,
            'keywords':analyze_keywords(keyword_records,plan['as_of_date']), 'pending_queries':pending,
            'candidate_count':len(products),'shortlist_count':len(shortlisted)}
    write_json(folder/'selection-evidence.json',report)
    review_path=folder/'selection-reviews.json'
    evidence_id=query_id({'plan':plan,'products':shortlisted,'keywords':report['keywords']})
    reviews=payload.get('reviews')
    if reviews is None and review_path.exists():
        stored=json.loads(review_path.read_text())
        if isinstance(stored,dict) and stored.get('evidence_id')==evidence_id: reviews=stored.get('reviews')
    reviews=reviews or []
    known={(p['marketplace'],p['asin']) for p in shortlisted}
    if any((r.get('marketplace'),r.get('asin')) not in known or type(r.get('relevant')) is not bool or not r.get('reason') for r in reviews):
        raise ValueError('reviews 必须对应本次 shortlist，包含 relevant 布尔值和证据理由')
    covered={(r['marketplace'],r['asin']) for r in reviews}
    waiting=[p for p in shortlisted if (p['marketplace'],p['asin']) not in covered]
    if reviews: write_json(review_path,{'evidence_id':evidence_id,'reviews':reviews})
    partial=any(r.get('collection_status')!='complete' for r in results)
    status='AWAITING_SCOPE' if plan['blocking_items'] else 'RUNNING' if pending else 'AWAITING_ANALYSIS' if waiting else 'PARTIAL' if partial else 'COMPLETE'
    if not products and not report['keywords']['directions'] and not pending and not plan['blocking_items']:
        status='BLOCKED' if partial else 'NO_CANDIDATES'
    output={'ok':True,'status':status,'run_dir':str(folder),'evidence_path':str(folder/'selection-evidence.json'),
            'blocking_items':plan['blocking_items'],'pending_queries':pending,'analysis_requests':waiting,
            'evidence_id':evidence_id,'counts':{'products':len(products),'shortlist':len(shortlisted),'keywords':len(report['keywords']['directions'])},
            'coverage':[{'source':r['query']['source'],'marketplace':r['query'].get('marketplace'),
                         'status':r.get('collection_status'),'reason':r.get('block_reason'),'rows':len(r.get('records',[]))} for r in results]}
    if not waiting and not pending and not plan['blocking_items'] and (products or report['keywords']['directions']):
        eligible=[p for p in shortlisted if not any(c['status']=='fail' for c in p.get('filter_checks',[]))]
        rows=summarize_products(eligible,reviews)
        missing={(p['marketplace'],p['asin']) for p in eligible if any(c['status']=='missing' for c in p.get('filter_checks',[]))}
        for row in rows:
            if (row['站点'],row['ASIN']) in missing: row['优先级']='待补数据';row['证据缺项']+='；筛选条件无法完整核实'
        if missing or any(row['优先级']=='待补数据' for row in rows):output['status']='PARTIAL'
        output['workbook']=export_workbook(folder/'开品结果.xlsx',rows,report)
        if output['workbook']['image_failures']: output['status']='PARTIAL'
    write_json(folder/'selection-status.json',output)
    return output
