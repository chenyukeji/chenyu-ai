"""Evidence-backed sales windows and review findings for selection workbooks.

Validate provenance/coverage, not whether the model's summary follows semantically.
"""
from datetime import date

from selection_analysis import month_index, number


ANALYSIS_REQUIREMENTS = {
    'lifecycle_analysis': '读取卖家精灵该商品历史月销量，优先24个月、至少12个完整连续月；写可售窗口与旺淡季，不用榜单命中月份或关键词热度替代。结构见 references/product-evidence.md。',
    'review_analysis': '读取真实买家评论，记录原文、日期、星级、来源和变体；按独立评论归纳产品缺点及样本频次。没有确切问题证据或归因不确定时缺点留空，不用结构特点、资料缺项或通用风险补位。无权限/无数据的实际阻塞记录到任务证据，不能标为已分析。',
}


def history_is_sufficient(history):
    """Require a full continuous year within one identified sales series."""
    if not history:
        return False
    months = [month_index(p.get('month')) for p in history]
    series = {(p.get('marketplace'), p.get('asin'), p.get('sales_scope')) for p in history}
    return (None not in months and len(months) >= 12 and len(set(months)) == len(months)
            and max(months) - min(months) + 1 == len(months) and len(series) == 1)


def _identity(record, item):
    identities = set(item.get('family_asins') or []) | {item['asin'], item.get('verified_parent_asin')}
    if record.get('marketplace') != item['marketplace'] or record.get('asin') not in identities:
        raise ValueError('分析证据必须匹配商品站点和已核实的父子体')
    if not str(record.get('source_ref') or '').strip():
        raise ValueError('分析证据缺少 source_ref')


def _state(value, field):
    if value is None:
        return 'missing'
    if not isinstance(value, dict) or value.get('status') not in ('analyzed', 'insufficient', 'unavailable'):
        raise ValueError(f'{field}.status 必须是 analyzed/insufficient/unavailable')
    if value['status'] != 'analyzed' and not str(value.get('reason') or '').strip():
        raise ValueError(f'{field} 数据不足时必须说明具体原因')
    return value['status']


def analysis_columns(item, review, as_of_date=None):
    """Return display values and missing analysis; legacy reviews remain readable."""
    cutoff = month_index(str(as_of_date or date.today().isoformat())[:7])
    if cutoff is None:
        raise ValueError('as_of_date must be an ISO date')
    lifecycle = review.get('lifecycle_analysis')
    life_state = _state(lifecycle, 'lifecycle_analysis')
    missing = []
    notes = []
    if life_state == 'missing':
        life_text = ''
        missing.append('历史销量分析未提交')
    else:
        history = lifecycle.get('history') or []
        if not isinstance(history, list):
            raise ValueError('lifecycle_analysis.history 必须是数组')
        months = set()
        series = set()
        sources = set()
        for point in history:
            if not isinstance(point, dict):
                raise ValueError('历史销量点必须是对象')
            _identity(point, item)
            month = month_index(point.get('month'))
            sales = number(point.get('estimated_sales'))
            if (month is None or month >= cutoff or point.get('period_complete') is not True
                    or sales is None or sales < 0 or point.get('sales_scope') not in ('parent', 'child')):
                raise ValueError('历史销量须为已完成月份、非负数且明确父/子体口径')
            if month in months:
                raise ValueError('同月历史销量不得重复或父子体相加')
            months.add(month)
            if point.get('value_kind', 'estimate') not in ('estimate', 'lower_bound', 'upper_bound'):
                raise ValueError('历史销量必须标明估算值、销量下限或上限')
            series.add((point['asin'], point['sales_scope']))
            sources.add(str(point['source_ref']))
        if len(series) > 1:
            raise ValueError('历史销量序列不能混合 ASIN 或父子体口径')
        if life_state == 'analyzed':
            if len(months) < 12 or max(months) - min(months) + 1 != len(months):
                raise ValueError('确认销售窗口需要至少12个完整连续月，缺月不补零；不足请标 insufficient')
            if not str(lifecycle.get('summary') or '').strip():
                raise ValueError('历史销量分析缺少 summary')
            life_text = lifecycle['summary']
        else:
            life_text = ''
            missing.append(f"生命周期：{lifecycle['reason']}")
        if months:
            if any(p.get('value_kind') == 'upper_bound' for p in history):
                notes.append('销量含网页显示的上限（小于号）；数值是边界而非精确销量，不用于精确增长率。')
            labels = sorted(str(p['month']) for p in history)
            notes.append(f'历史月销依据：{labels[0]}至{labels[-1]}，{len(months)}个完整月；' + '、'.join(sorted(sources)))
            if any(p.get('value_kind') == 'lower_bound' for p in history):
                notes.append('销量含网页显示的下限值（加号），不代表精确销量，不能据此计算精确增长率。')

    comments = review.get('review_analysis')
    comment_state = _state(comments, 'review_analysis')
    if comment_state == 'missing':
        cons = ''
        missing.append('评论分析未提交')
    elif comment_state != 'analyzed':
        cons = ''
        missing.append(f"评论：{comments['reason']}")
    else:
        samples = comments.get('samples')
        findings = comments.get('findings')
        if not isinstance(samples, list) or not samples or not isinstance(findings, list):
            raise ValueError('评论分析需要非空 samples 和 findings 数组')
        ids = set()
        for sample in samples:
            if not isinstance(sample, dict):
                raise ValueError('评论样本必须是对象')
            _identity(sample, item)
            identifier = str(sample.get('review_id') or '').strip()
            rating = number(sample.get('rating'))
            try:
                date.fromisoformat(str(sample.get('date')))
            except ValueError:
                raise ValueError('评论样本需要有效日期') from None
            if not identifier or identifier in ids or not str(sample.get('text') or '').strip() or rating is None or not 1 <= rating <= 5:
                raise ValueError('评论样本需要独立 ID、原文和1–5星评分；重复评论不能重复计数')
            ids.add(identifier)
        if not str(comments.get('sampling_scope') or '').strip():
            raise ValueError('评论分析须说明 sampling_scope，不以差评样本代表全部评论')
        parts = []
        for finding in findings:
            if not isinstance(finding, dict) or not str(finding.get('summary') or '').strip():
                raise ValueError('缺点分析须填写 summary')
            cited = finding.get('review_ids')
            if not isinstance(cited, list) or not cited or any(not isinstance(x, str) for x in cited):
                raise ValueError('每项缺点必须引用实际评论 ID')
            if len(set(cited)) != len(cited) or not set(cited) <= ids:
                raise ValueError('缺点引用了缺失或重复的评论')
            parts.append(f"{finding['summary']}（所读样本 {len(cited)}/{len(ids)} 条）")
        cons = '；'.join(parts)
        if not parts:
            notes.append(f'已读{len(ids)}条评论，样本内未归纳出明确产品缺点')
        notes.append(f"评论采样范围：{comments['sampling_scope']}；样本频次不代表全部买家。")
        notes.append('评论依据：' + '、'.join(dict.fromkeys(str(s['source_ref']) for s in samples)))
    return {'生命周期': life_text, '缺点': cons, 'analysis_missing': missing, 'analysis_notes': notes}
