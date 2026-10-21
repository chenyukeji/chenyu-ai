import importlib.util
from pathlib import Path


SCRIPT = (Path(__file__).resolve().parents[1] /
          'plugins/chenyu-yunying/skills/chenyu-listing/scripts/collect_sellersprite_keywords.py')
SPEC = importlib.util.spec_from_file_location('collect_sellersprite_keywords', SCRIPT)
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def test_market_ids_match_verified_sellersprite_selector():
    assert COLLECTOR.MARKET_IDS == {
        'US': 1, 'UK': 3, 'DE': 4, 'FR': 5, 'IT': 35691, 'ES': 44551
    }


def test_request_rejects_invalid_market_and_asin():
    assert COLLECTOR.parse_request('de:B0BJFJ3J3S') == ('DE', 'B0BJFJ3J3S')
    for value in ('US:not-an-asin', 'XX:B0BJFJ3J3S', 'B0BJFJ3J3S'):
        try:
            COLLECTOR.parse_request(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f'{value} should be rejected')


def test_mid_batch_failure_preserves_success_and_not_run(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock
    output = tmp_path / 'checkpoint.json'
    context, page = MagicMock(), MagicMock()
    monkeypatch.setattr(COLLECTOR, 'launch_context', lambda *a: (context, page, None))
    monkeypatch.setattr(COLLECTOR, 'login', lambda *a: None)
    seen = []
    def collect(page, market, asin):
        seen.append(market)
        if market == 'IT':
            assert len(json.loads(output.read_text())['queries']) == 1
            raise COLLECTOR.SessionError('sellersprite_account_locked')
        return {'marketplace': market, 'asin': asin, 'rows': [{'keyword': 'boucles'}]}
    monkeypatch.setattr(COLLECTOR, 'collect', collect)
    requests = [('FR', 'B000000001'), ('IT', 'B000000002'), ('ES', 'B000000003')]
    COLLECTOR.collect_requests(requests, output, MagicMock(), 'fake', 'secret')
    data = json.loads(output.read_text())
    assert seen == ['FR', 'IT']
    assert data['failures'][0]['reason'] == 'sellersprite_account_locked'
    assert data['pending'] == [{'marketplace': 'ES', 'asin': 'B000000003', 'status': 'not_run'}]
    context.close.assert_called_once()
    assert 'secret' not in output.read_text()


def test_launch_block_keeps_all_requests_pending(tmp_path, monkeypatch):
    import json
    from unittest.mock import MagicMock
    def launch(*a):
        raise COLLECTOR.SessionError('sellersprite_account_locked')
    monkeypatch.setattr(COLLECTOR, 'launch_context', launch)
    output = tmp_path / 'blocked.json'
    COLLECTOR.collect_requests([('FR', 'B000000001')], output, MagicMock(), 'fake', 'secret')
    data = json.loads(output.read_text())
    assert data['queries'] == []
    assert len(data['pending']) == 1
    assert data['failures'][0]['reason'] == 'sellersprite_account_locked'
