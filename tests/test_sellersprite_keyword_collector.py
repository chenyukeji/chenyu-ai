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
