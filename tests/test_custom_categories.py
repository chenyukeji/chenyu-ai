"""Custom category collection and v3 resume behavior; network responses are fixtures."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('custom_category_run', SCRIPTS / 'run.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)
from category_sources import CategoryInputError, normalize_url, resolve_sources


def category(name, suffix):
    # Synthetic paths test the contract; they are not verified live category nodes.
    return {'name': name, 'amazon_new_releases': {
        'US': f'https://www.amazon.com/gp/new-releases/{suffix}',
        'DE': f'https://www.amazon.de/gp/new-releases/{suffix}',
    }}


def task_for(categories):
    return run.create_task('自定义选品，不按派对用品预设', {'categories': categories})


def test_explicit_arbitrary_categories_override_request_presets():
    task = task_for([category('自定义厨房细分类目', 'fixture-kitchen'), category('庭院园艺', 'fixture-garden')])
    sources = resolve_sources(task['category_resolution'], ['US', 'DE'])
    assert len(sources) == 4
    assert {s['category'] for s in sources} == {'自定义厨房细分类目', '庭院园艺'}
    assert all('fixture-' in s['url'] for s in sources)
    assert task['flow_version'] == 'discovery-v3'


@pytest.mark.parametrize('unsupported', [{'category_or_need': '厨房'}, {'amazon_new_releases': {}}])
def test_unsupported_task_fields_are_rejected(unsupported):
    with pytest.raises(run.ContractError, match='unsupported task fields'):
        run.create_task('厨房', unsupported)


def test_unsupported_discovery_field_and_incompatible_run_directory_are_rejected(tmp_path):
    with pytest.raises(run.ContractError, match='unsupported discovery fields'):
        run.run_discovery_flow({'request': '厨房', 'run_dir': str(tmp_path), 'discovery': {'amazon_new_releases': {}}})
    incompatible = {'task_id': 'old', 'category_resolution': {'amazon_new_releases': {}}}
    (tmp_path / '02-task.json').write_text(json.dumps(incompatible))
    with pytest.raises(run.ContractError, match='run_dir flow_version does not match'):
        run.run_discovery_flow({'run_dir': str(tmp_path)})
    assert json.loads((tmp_path / '02-task.json').read_text()) == incompatible


@pytest.mark.parametrize('url', [
    'https://www.amazon.de/gp/new-releases/kitchen',
    'https://www.amazon.com/gp/bestsellers/kitchen',
    'https://www.amazon.com/gp/new-releases/',
    'https://www.amazon.com/gp/new-releases/ref=zg',
    'https://amazon.com.example.org/gp/new-releases/kitchen',
])
def test_wrong_market_or_non_category_urls_are_rejected(url):
    with pytest.raises(CategoryInputError):
        normalize_url(url, 'US')


def test_missing_category_market_stops_before_collecting(monkeypatch, tmp_path):
    second = category('庭院', 'fixture-garden')
    del second['amazon_new_releases']['DE']
    monkeypatch.setattr(run, 'collect', lambda _: pytest.fail('must validate all sources before collecting'))
    result = run.run_discovery_flow({'request': '厨房庭院', 'run_dir': str(tmp_path),
                                    'task': {'categories': [category('厨房', 'fixture-kitchen'), second]}})
    assert result['status'] == 'AWAITING_CATEGORY_INPUT'
    assert '庭院 / DE' in result['blocking_items'][0]
    assert not (tmp_path / '09-screening.json').exists()


def test_multiple_urls_deduplicate_and_balance_market_limit(monkeypatch, tmp_path):
    first, second = category('厨房', 'fixture-kitchen'), category('庭院', 'fixture-garden')
    first['amazon_new_releases']['US'] = [first['amazon_new_releases']['US'], first['amazon_new_releases']['US'] + '?ref=x']
    calls = []
    def collect(payload):
        calls.append(payload)
        is_kitchen = payload['query'] == '厨房'
        return {'records': [
            {'asin': 'B0SHARED01', 'new_release_rank': 1},
            {'asin': 'B0KITCH001' if is_kitchen else 'B0GARDN001', 'new_release_rank': 2},
        ]}
    monkeypatch.setattr(run, 'collect', collect)
    task = task_for([first, second])
    manifest = {'artifacts': {}, 'warnings': []}
    records = run._live_strategy_e(task, {'discovery': {'limit_per_marketplace': 3}}, tmp_path, manifest)
    assert len(calls) == 4
    assert len(records) == 6
    for market in ('US', 'DE'):
        rows = [r for r in records if r['marketplace'] == market]
        assert {r['asin'] for r in rows} == {'B0SHARED01', 'B0KITCH001', 'B0GARDN001'}
        assert len(next(r for r in rows if r['asin'] == 'B0SHARED01')['source_refs']) == 2
    assert len(run.merge_candidates(records)) == 6
    run._live_strategy_e(task, {'discovery': {'limit_per_marketplace': 3}}, tmp_path, {'artifacts': {}, 'warnings': []})
    assert len(calls) == 4
    second['amazon_new_releases']['US'] += '-new'
    run._live_strategy_e(task_for([first, second]), {'discovery': {'limit_per_marketplace': 3}}, tmp_path, {'artifacts': {}, 'warnings': []})
    assert len(calls) == 5  # Only the changed source is recollected.


def test_resume_applies_new_categories_and_never_reuses_previous_candidates(monkeypatch, tmp_path):
    calls = []
    empty = set()
    def collect(payload):
        calls.append(payload['url'])
        if payload['query'] in empty:
            return {'records': []}
        return {'records': [{'asin': 'B0KITCH001' if payload['query'] == '厨房' else 'B0GARDN001', 'new_release_rank': 2}]}
    def enrich(records, *_):
        return [{**row, 'product_name': row['category_name'], 'review_count': 8, 'price': 15,
                 'source_available_date': '2026-09-01', 'estimated_sales': 400, 'bsr': 100} for row in records]
    monkeypatch.setattr(run, 'collect', collect)
    monkeypatch.setattr(run, '_enrich_records_from_sellersprite', enrich)
    payload = {'request': '厨房庭院', 'run_dir': str(tmp_path), 'as_of_date': '2026-09-24'}
    assert run.run_discovery_flow(payload)['status'] == 'AWAITING_CATEGORY_INPUT'
    task_id = json.loads((tmp_path / '02-task.json').read_text())['task_id']
    payload['task'] = {'categories': [category('厨房', 'fixture-kitchen')]}
    result = run.run_discovery_flow(payload)
    assert result['status'] == 'COMPLETE'
    assert Path(result['workbook']['path']).is_file()
    assert json.loads((tmp_path / '02-task.json').read_text())['task_id'] == task_id
    # A changed source that temporarily returns no data must not resurrect old kitchen records.
    empty.add('庭院')
    payload['task'] = {'categories': [category('庭院', 'fixture-garden')]}
    assert run.run_discovery_flow(payload)['status'] == 'NO_CANDIDATES'
    payload.pop('task')
    assert run.run_discovery_flow(payload)['status'] == 'NO_CANDIDATES'
    empty.clear()
    assert run.run_discovery_flow(payload)['status'] == 'COMPLETE'
    records = json.loads((tmp_path / '07-source-records.json').read_text())['records']
    assert {r['asin'] for r in records} == {'B0GARDN001'}
    assert len(calls) == 8
