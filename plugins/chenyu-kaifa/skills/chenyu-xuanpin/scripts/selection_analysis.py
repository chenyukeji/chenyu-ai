"""Evidence analysis for the single selection skill; no network or invented scores."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import re


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).replace(',', '').replace('%', '').strip())
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def month_index(value):
    text = str(value or '').strip()
    match = re.fullmatch(r'(\d{4})[-年/](\d{1,2})月?', text)
    if not match or not 1 <= int(match[2]) <= 12:
        return None
    return int(match[1]) * 12 + int(match[2]) - 1


def month_label(index):
    return f'{index // 12:04d}-{index % 12 + 1:02d}'


def growth(current, previous):
    if current is None or previous is None or previous <= 0:
        return None
    return round((current / previous - 1) * 100, 2)


def analyze_keywords(records, as_of_date):
    """Keep keyword demand independent of ASINs; compare complete, same-period months."""
    current_month = month_index(str(as_of_date)[:7])
    if current_month is None:
        raise ValueError('as_of_date must be an ISO date')
    groups = defaultdict(dict)
    rejected = []
    for row in records:
        keyword = str(row.get('keyword') or '').strip()
        market = str(row.get('marketplace') or '').upper()
        month = month_index(row.get('month') or row.get('search_period'))
        volume = number(row.get('search_volume'))
        if not keyword or not market or month is None or volume is None or volume < 0 or not row.get('source_ref'):
            rejected.append({'reason': 'keyword_identity_period_volume_or_source_missing'})
            continue
        # Missing completeness defaults only for past calendar months; current months excluded.
        if month >= current_month or row.get('period_complete') is False:
            continue
        key = (market, keyword.casefold())
        existing = groups[key].get(month)
        item = {**row, 'keyword': keyword, 'month': month_label(month), 'search_volume': volume}
        if existing and existing['search_volume'] != volume:
            existing.setdefault('conflicts', []).append(item)
        elif not existing:
            groups[key][month] = item
    directions = []
    for (market, _), months in groups.items():
        latest = max(months)
        row = months[latest]
        volume = row['search_volume']
        previous = months.get(latest - 1, {}).get('search_volume')
        prior_year = months.get(latest - 12, {}).get('search_volume')
        recent = [months.get(latest - offset, {}).get('search_volume') for offset in (2, 1, 0)]
        conflicts = any(x.get('conflicts') for x in months.values())
        evidence = ['搜索需求不等同于商品销量；关联词搜索量不相加']
        mom, yoy = growth(volume, previous), growth(volume, prior_year)
        if mom is not None:
            evidence.append(f'环比 {mom:+g}%，绝对变化 {volume - previous:+g}')
        if yoy is not None:
            evidence.append(f'同比 {yoy:+g}%')
        if all(v is not None for v in recent):
            evidence.append('连续两次月度增长' if recent[0] < recent[1] < recent[2] else '最近三个月并非持续上升')
        years = defaultdict(dict)
        for index, value in months.items():
            years[index // 12][index % 12 + 1] = value['search_volume']
        full_years = {year: values for year, values in years.items() if len(values) == 12}
        peaks = {str(year): max(values, key=values.get) for year, values in full_years.items()}
        if len(peaks) < 2:
            evidence.append('完整年度不足两年，不能确认重复季节性')
        else:
            evidence.append('完整年度峰值月份：' + '、'.join(f'{year}年{month}月' for year, month in peaks.items()))
        if conflicts:
            evidence.append('同词同月搜索量存在冲突，需核实后判断')
            mom = yoy = None
        directions.append({'marketplace': market, 'keyword': row['keyword'], 'latest_month': row['month'],
                           'search_volume': volume, 'mom_percent': mom, 'yoy_percent': yoy,
                           'absolute_change': volume - previous if previous is not None and not conflicts else None,
                           'history': [months[i] for i in sorted(months)], 'yearly_peak_months': peaks,
                           'confidence': '待核实' if conflicts else '历史较充分' if len(months) >= 24 else '有限',
                           'evidence': evidence, 'data_lag_months': current_month - latest - 1})
    return {'directions': directions, 'rejected': rejected}


def merge_products(source_results, *, associations=None):
    """Preserve time/source observations instead of overwriting history with current values."""
    groups = {}
    for result in source_results:
        spec = result.get('query') or {}
        source = spec.get('source') or result.get('source')
        for raw_row in result.get('records') or []:
            row=dict(raw_row)
            for field in ('price','estimated_sales','review_count'):
                if field in row:row[field]=number(row[field])
            if 'source_available_date' in row:
                try: row['source_available_date']=date.fromisoformat(str(row['source_available_date'])).isoformat()
                except (ValueError,TypeError):row['source_available_date']=None
            asin = str(row.get('asin') or '').upper()
            market = str(row.get('marketplace') or spec.get('marketplace') or '').upper()
            if not re.fullmatch(r'[A-Z0-9]{10}', asin) or not market:
                continue
            key = (market, asin)
            item = groups.setdefault(key, {'marketplace': market, 'asin': asin, 'observations': [], 'source_types': [],
                                           'current': {}, 'historical': [], 'stores': [], 'keywords': []})
            observation = {**row, 'source_type': source, 'query_id': spec.get('id')}
            if observation not in item['observations']:
                item['observations'].append(observation)
            if source not in item['source_types']:
                item['source_types'].append(source)
            month = row.get('history_month') or spec.get('history_month')
            if month:
                historical = {**observation, 'history_month': month}
                if historical not in item['historical']:
                    item['historical'].append(historical)
            elif source != 'new_releases_db':
                # Enrichment has precedence, but raw conflicting observations remain available.
                for field, value in row.items():
                    if value is not None and (source == 'sellersprite_enrichment' or field not in item['current']):
                        item['current'][field] = value
            if row.get('seller_id'):
                store = {'seller_id': row['seller_id'], 'source_ref': row.get('source_ref')}
                if store not in item['stores']:
                    item['stores'].append(store)
    for link in associations or []:
        key = (str(link.get('marketplace') or '').upper(), str(link.get('asin') or '').upper())
        if key in groups and link.get('keyword') and link.get('source_ref') and link.get('relation'):
            if link not in groups[key]['keywords']:
                groups[key]['keywords'].append(link)
    return list(groups.values())


def summarize_products(products, reviews=None):
    """A model reviews relevance and opportunity; unknown relevance is never silently accepted."""
    reviews = reviews or []
    index = {(r.get('marketplace'), r.get('asin')): r for r in reviews}
    output = []
    for item in products:
        review = index.get((item['marketplace'], item['asin']), {})
        if review.get('relevant') is False:
            continue
        current = item['current']
        missing = [field for field in ('source_available_date', 'review_count', 'price', 'estimated_sales')
                   if current.get(field) is None]
        verified = review.get('relevant') is True and bool(review.get('reason'))
        decision = review.get('priority') if verified and not missing else '待补数据' if missing else '待核对相关性'
        if decision not in ('优先研究', '继续观察', '低优先级', '待补数据', '待核对相关性'):
            raise ValueError('unsupported priority')
        row = {'站点': item['marketplace'], 'ASIN': item['asin'], '产品名称': current.get('product_name') or next(
            (r.get('product_name') or r.get('title') for r in item['observations'] if r.get('product_name') or r.get('title')), ''),
            '图片': current.get('image_url'), '所在品类': current.get('category_name'),
            '售价': current.get('price'), '币种': current.get('currency'), '评论量': current.get('review_count'),
            '当前预估月销量': current.get('estimated_sales'), '销量口径': '父体或来源口径，未跨变体求和',
            '上架日期': current.get('source_available_date'), '命中来源': '、'.join(SOURCE_LABELS.get(source,source) for source in item['source_types']),
            '店铺来源': '、'.join(x['seller_id'] for x in item['stores']),
            '历史命中月份': '、'.join(sorted({x['history_month'] for x in item['historical']})),
            '关联关键词': '、'.join(dict.fromkeys(x['keyword'] for x in item['keywords'])),
            '优先级': decision, '分析': review.get('reason') if verified else '等待模型核对产品用途与用户范围',
            '证据缺项': '、'.join(missing), '亚马逊产品链接': current.get('detail_url') or
                f"https://www.amazon.{'de' if item['marketplace']=='DE' else 'com'}/dp/{item['asin']}"}
        output.append(row)
    order = {'优先研究': 0, '继续观察': 1, '低优先级': 2, '待补数据': 3, '待核对相关性': 4}
    return sorted(output, key=lambda x: (order[x['优先级']], x['站点'], x['ASIN']))


SOURCE_LABELS = {
    'amazon_input':'商品或店铺入口','amazon_new_releases':'亚马逊新品榜',
    'sellersprite_new':'卖家精灵研发新品榜','sellersprite_surge':'卖家精灵当前销量飙升榜',
    'sellersprite_history':'卖家精灵历史销量飙升榜','keyword_trends':'关键词历史趋势',
    'keyword_products':'关键词关联商品','new_releases_db':'新品历史数据库',
    'sellersprite_enrichment':'卖家精灵商品补数',
}


def lexical_fit(item):
    scores=[]
    for row in item['observations']:
        tokens=set(re.findall(r'[a-z0-9äöüß]+',str(row.get('filter_keyword') or '').casefold()))
        text=' '.join(str(row.get(f) or '') for f in ('product_name','title','category_name')).casefold()
        if tokens:scores.append(sum(token in text for token in tokens)/len(tokens))
    return max(scores,default=0)


def balanced_shortlist(products, limit):
    groups = defaultdict(list)
    for item in products:
        for source in item['source_types']:
            if source!='sellersprite_enrichment':groups[(item['marketplace'],source)].append(item)
    for group in groups.values():group.sort(key=lexical_fit,reverse=True)
    chosen=[];seen=set()
    while len(chosen)<limit:
        changed=False
        for group in groups.values():
            while group and (group[0]['marketplace'],group[0]['asin']) in seen:group.pop(0)
            if group and len(chosen)<limit:
                item=group.pop(0);chosen.append(item);seen.add((item['marketplace'],item['asin']));changed=True
        if not changed:break
    return chosen
