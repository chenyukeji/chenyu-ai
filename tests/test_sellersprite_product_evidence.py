from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'))
from sellersprite_product_evidence import parse_monthly_table, collect_product_evidence


def table(values):
    return {'headers': ['', '2026-01', '2026-02', '2026-03', '2026-10', ''],
            'rows': [['', '$500', '$600', '$700', '$800'], ['', *values]],
            'labels': ['月销售额', '月销量']}


def parse(value, **kwargs):
    return parse_monthly_table(value, marketplace='US', asin='B07XW1MJD8',
        source_ref='https://www.sellersprite.com/v3/competitor-lookup', as_of_date='2026-10-13', **kwargs)


def test_parent_months_match_sales_row_and_exclude_current_month():
    points, missing = parse(table(['58', '75', '0', '403']))
    assert [(p['month'], p['estimated_sales']) for p in points] == [('2026-01', 58), ('2026-02', 75), ('2026-03', 0)]
    assert all(p['sales_scope'] == 'parent' and p['period_complete'] for p in points)
    assert missing == []


def test_child_thresholds_remain_lower_bounds_not_exact_sales():
    points, missing = parse(table(['100,000+', '80K+', 'N/A', '100,000+']), sales_scope='child')
    assert [p['estimated_sales'] for p in points] == [100000, 80000]
    assert [p['sales_display'] for p in points] == ['100,000+', '80K+']
    assert all(p['value_kind'] == 'lower_bound' and p['sales_scope'] == 'child' for p in points)
    assert missing == ['2026-03']


def test_missing_cells_do_not_become_zero_and_duplicate_months_fail():
    points, missing = parse(table(['-', '', '25', '50']))
    assert len(points) == 1 and points[0]['estimated_sales'] == 25
    assert missing == ['2026-01', '2026-02']
    value = table(['10', '20', '30', '40']); value['headers'][2] = '2026-01'
    with pytest.raises(ValueError, match='duplicate_history_month'):
        parse(value)


def test_revenue_only_table_cannot_be_mislabeled_as_sales():
    value = table(['1', '2', '3', '4']); value['labels'] = ['月销售额', '平均单价']
    with pytest.raises(ValueError, match='monthly_sales_row_unverified'):
        parse(value)


@pytest.mark.parametrize('payload', [
    {'marketplace': 'US', 'asins': []},
    {'marketplace': 'US', 'asins': ['../bad']},
    {'marketplace': 'FR', 'asins': ['B07XW1MJD8']},
    {'marketplace': 'US', 'asins': ['B07XW1MJD8'], 'sales_scope': 'sum'},
])
def test_invalid_request_fails_before_launching_browser(payload):
    with pytest.raises(ValueError):
        collect_product_evidence(payload)
