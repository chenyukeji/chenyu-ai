from copy import deepcopy
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'
sys.path.insert(0, str(SCRIPTS))
from product_evidence import analysis_columns
from selection_flow import original_style_rows


def item():
    return {'marketplace': 'US', 'asin': 'B012345678', 'current': {}}


def analysis():
    identity = {**item(), 'source_ref': 'https://www.sellersprite.com/fixture'}
    return {
        'marketplace': 'US', 'asin': 'B012345678',
        'lifecycle_analysis': {
            'status': 'analyzed', 'summary': '2025年全年有销量，10–12月较高',
            'history': [{**identity, 'month': f'2025-{month:02}', 'estimated_sales': 500 if month >= 10 else 100,
                         'period_complete': True, 'sales_scope': 'parent'} for month in range(1, 13)],
        },
        'review_analysis': {
            'status': 'analyzed', 'sampling_scope': '2026年9月可读取的2条评论，含低星与高星，当前款式',
            'samples': [
                {**identity, 'review_id': 'R1', 'date': '2026-09-10', 'rating': 2, 'text': 'The fan is noisy.'},
                {**identity, 'review_id': 'R2', 'date': '2026-09-11', 'rating': 5, 'text': 'Works well.'},
            ],
            'findings': [{'summary': '有买家反映风扇噪声', 'review_ids': ['R1']}],
        },
    }


def test_evidence_reaches_original_workbook_columns():
    report = {'products': [item()], 'reviews': [analysis()], 'plan': {'as_of_date': '2026-10-13'}}
    result = original_style_rows([{'站点': 'US', 'ASIN': 'B012345678', '分析': '室内取暖用途'}], report)[0]
    assert result['生命周期'] == '2025年全年有销量，10–12月较高'
    assert result['缺点'] == '有买家反映风扇噪声（所读样本 1/2 条）'
    assert '2025-01至2025-12' in result['理由'] and '样本频次不代表全部买家' in result['理由']


def test_missing_data_differs_from_reviewed_without_findings():
    missing = analysis_columns(item(), {}, '2026-10-13')
    assert len(missing['analysis_missing']) == 2
    assert missing['缺点'] == missing['生命周期'] == ''
    done = analysis(); done['review_analysis']['findings'] = []
    reviewed = analysis_columns(item(), done, '2026-10-13')
    assert reviewed['缺点'] == '' and not reviewed['analysis_missing']
    assert any('已读2条' in note for note in reviewed['analysis_notes'])


def test_unavailable_data_keeps_reason():
    blocked = {'lifecycle_analysis': {'status': 'unavailable', 'reason': '历史曲线权限不足'},
               'review_analysis': {'status': 'unavailable', 'reason': '评论页面要求验证'}}
    result = analysis_columns(item(), blocked, '2026-10-13')
    assert result['生命周期'] == result['缺点'] == ''
    assert any('权限不足' in reason for reason in result['analysis_missing'])
    assert any('要求验证' in reason for reason in result['analysis_missing'])
    assert len(result['analysis_missing']) == 2


@pytest.mark.parametrize('problem', ['short', 'gap', 'duplicate', 'current', 'scope', 'wrong_asin', 'negative'])
def test_invalid_history_cannot_claim_full_window(problem):
    data = analysis(); history = data['lifecycle_analysis']['history']
    if problem == 'short': history.pop()
    if problem == 'gap': history[-1]['month'] = '2026-01'
    if problem == 'duplicate': history[-1] = deepcopy(history[0])
    if problem == 'current': history[-1]['month'] = '2026-10'
    if problem == 'scope': history[-1]['sales_scope'] = 'child'
    if problem == 'wrong_asin': history[-1]['asin'] = 'B099999999'
    if problem == 'negative': history[-1]['estimated_sales'] = -1
    with pytest.raises(ValueError): analysis_columns(item(), data, '2026-10-13')


def test_short_history_can_report_limited_observation():
    data = analysis(); life = data['lifecycle_analysis']
    life.update(status='insufficient', reason='仅有两个月记录', summary='这两个月销量上升', history=life['history'][:2])
    result = analysis_columns(item(), data, '2026-10-13')
    assert '有限观察' in result['生命周期'] and len(result['analysis_missing']) == 1


@pytest.mark.parametrize('problem', ['duplicate', 'unknown_id', 'repeated_id', 'no_text', 'wrong_market', 'no_scope'])
def test_review_counts_require_unique_real_sample_mappings(problem):
    data = analysis(); reviews = data['review_analysis']
    if problem == 'duplicate': reviews['samples'].append(deepcopy(reviews['samples'][0]))
    if problem == 'unknown_id': reviews['findings'][0]['review_ids'] = ['R999']
    if problem == 'repeated_id': reviews['findings'][0]['review_ids'] = ['R1', 'R1']
    if problem == 'no_text': reviews['samples'][0]['text'] = ''
    if problem == 'wrong_market': reviews['samples'][0]['marketplace'] = 'DE'
    if problem == 'no_scope': del reviews['sampling_scope']
    with pytest.raises(ValueError): analysis_columns(item(), data, '2026-10-13')


def test_lower_bound_sales_are_disclosed_in_workbook_evidence():
    data = analysis()
    for point in data['lifecycle_analysis']['history']:
        point.update(value_kind='lower_bound', sales_display='100+')
    result = analysis_columns(item(), data, '2026-10-13')
    assert any('下限值' in note for note in result['analysis_notes'])
    data['lifecycle_analysis']['history'][0]['value_kind'] = 'exact'
    with pytest.raises(ValueError, match='销量下限'):
        analysis_columns(item(), data, '2026-10-13')
