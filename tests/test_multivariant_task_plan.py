import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'plugins/chenyu-meigong/skills/chenyu-zuotu/scripts/validate_task_plan.py'
SPEC = importlib.util.spec_from_file_location('validate_task_plan', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def plan(shared=False, legacy_rows=False):
    data = {'brief_blocks': [], 'tasks': []}
    for number in range(7):
        products = ['A', 'B']
        rows = [[p] for p in products] if legacy_rows else [products]
        for row in rows:
            bid = f'row-{number}-' + '-'.join(row)
            block = {'id': bid, 'product_ids': row, 'outputs': []}
            groups = [row] if shared and number == 4 else [[p] for p in row]
            for group in groups:
                tid = bid + '-' + '-'.join(group)
                block['outputs'].append({'task_id': tid, 'product_ids': group})
                data['tasks'].append({'id': tid, 'brief_task_id': bid, 'product_ids': group})
            data['brief_blocks'].append(block)
    return data


def test_seven_grouped_rows_and_fourteen_legacy_rows_both_route_fourteen_outputs():
    for legacy in [False, True]:
        data = plan(legacy_rows=legacy)
        assert len(data['tasks']) == 14
        assert MODULE.validate(data)['valid']


def test_explicit_shared_output_is_counted_once():
    data = plan(shared=True)
    assert len(data['tasks']) == 13
    assert MODULE.validate(data)['valid']


def test_missing_extra_or_wrong_variant_outputs_are_rejected():
    data = plan()
    data['tasks'].pop()
    assert not MODULE.validate(data)['valid']
    data = plan()
    extra = copy.deepcopy(data['tasks'][0])
    extra['id'] = 'extra'
    data['tasks'].append(extra)
    assert not MODULE.validate(data)['valid']
    data = plan()
    data['tasks'][0]['product_ids'] = ['B']
    assert not MODULE.validate(data)['valid']


def test_partial_variant_scope_is_not_expanded():
    data = plan()
    data['brief_blocks'][0]['product_ids'] = ['A']
    data['brief_blocks'][0]['outputs'].pop()
    data['tasks'].pop(1)
    assert len(data['tasks']) == 13
    assert MODULE.validate(data)['valid']


def test_legacy_plan_explicitly_reports_unchecked_routing():
    result = MODULE.validate({'tasks': [{'id': 'old-1', 'product_id': 'A'}]})
    assert result['valid'] and result['warnings']
