import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import playwright_collector as collector
import discovery_pipeline as pipeline
import run

ASIN = 'B0HCBQ5SDF'

class Response:
    def __init__(self, data=None, code='OK', status=200, asin=ASIN):
        self.url = 'https://www.sellersprite.com/v3/api/competing-lookup'
        self.request = SimpleNamespace(url=self.url, post_data=json.dumps({'asins': [asin]}))
        self.status = status
        self.body = {'code': code, 'data': data or {'items': [], 'total': 0}}
    def json(self):
        return self.body

class FakePage:
    def __init__(self, delay=0.6, response=None):
        self.now = 0
        self.delay = delay
        self.response = response
        self.listeners = {}
    def on(self, event, handler):
        self.listeners[event] = handler
    def remove_listener(self, event, handler):
        self.listeners.pop(event)
    def wait_for_timeout(self, ms):
        self.now += ms / 1000
        if self.response is not None and self.now >= self.delay:
            response, self.response = self.response, None
            self.listeners['response'](response)

class ReliabilityTests(unittest.TestCase):
    def query(self, page, rows=None, state='authenticated'):
        with patch.object(collector.time, 'monotonic', side_effect=lambda: page.now), \
             patch.object(collector, '_challenge_visible', return_value=False), \
             patch.object(collector, '_sellersprite_auth_state', return_value=state), \
             patch.object(collector, 'extract_sellersprite_table', return_value=rows or []):
            result = collector._wait_sellersprite_query(page, {}, 'DE', [ASIN], lambda: None, 8000, 200)
        self.assertEqual(page.listeners, {})
        return result

    def test_editable_input_does_not_authenticate_guest(self):
        page = MagicMock()
        page.locator.return_value.first.count.return_value = 1
        page.locator.return_value.first.inner_text.return_value = '未登录'
        field = MagicMock()
        field.count.return_value = 1
        field.is_disabled.return_value = False
        self.assertEqual(collector._sellersprite_login_block_reason(page, field), 'sellersprite_login_required')

    def test_show_all_variants_is_disabled_before_query(self):
        for initially_checked in (False, True):
            with self.subTest(initially_checked=initially_checked):
                page = MagicMock()
                label = page.locator.return_value.filter.return_value.first
                label.count.return_value = 1
                label.is_visible.return_value = True
                checkbox = label.locator.return_value.first
                checkbox.count.return_value = 1
                checkbox.is_checked.side_effect = [initially_checked, False]
                collector._ensure_sellersprite_variants_off(page)
                self.assertEqual(label.click.call_count, int(initially_checked))

    def test_missing_or_stuck_variants_checkbox_stops_query(self):
        page = MagicMock()
        label = page.locator.return_value.filter.return_value.first
        label.count.return_value = 0
        with self.assertRaises(collector.BrowserCollectionError):
            collector._ensure_sellersprite_variants_off(page)
        label.count.return_value = 1
        label.is_visible.return_value = True
        checkbox = label.locator.return_value.first
        checkbox.count.return_value = 1
        checkbox.is_checked.return_value = True
        with self.assertRaises(collector.BrowserCollectionError):
            collector._ensure_sellersprite_variants_off(page)

    def test_batch_search_uses_page_input_after_disabling_variants(self):
        page = MagicMock()
        asin_input = MagicMock()
        other = 'B0HBQ6N1ZC'
        with patch.object(collector, '_ensure_sellersprite_variants_off') as disable, \
             patch.object(collector, '_wait_for_sellersprite_asin_input', return_value=asin_input), \
             patch.object(collector, '_wait_sellersprite_query', side_effect=lambda *args: args[4]()):
            collector._query_sellersprite_batch(page, {}, 'US', [ASIN, other], 8000, 200, 800)
        disable.assert_called_once_with(page)
        asin_input.fill.assert_called_once_with(f'{ASIN},{other}')
        page.get_by_role.return_value.first.click.assert_called_once()

    def test_single_search_disables_variants_before_submitting(self):
        page = MagicMock()
        asin_input = MagicMock()
        def query(_page, _payload, _marketplace, _asins, trigger, *_):
            trigger()
            return [], 50, 'confirmed_empty'
        with patch.object(collector, '_require_playwright', return_value=MagicMock()), \
             patch.object(collector, '_launch_context', return_value=(MagicMock(), page, Path('/tmp/profile'))), \
             patch.object(collector, '_sellersprite_credentials', return_value=('', '', None)), \
             patch.object(collector, '_wait_for_sellersprite_session', return_value=None), \
             patch.object(collector, '_select_sellersprite_market', return_value='美国站'), \
             patch.object(collector, '_goto'), \
             patch.object(collector, '_ensure_sellersprite_variants_off') as disable, \
             patch.object(collector, '_wait_for_sellersprite_asin_input', return_value=asin_input), \
             patch.object(collector, '_wait_sellersprite_query', side_effect=query):
            collector.collect_sellersprite_by_asin({'marketplace': 'US', 'asins': [ASIN], 'query_delay_ms': 0})
        disable.assert_called_once_with(page)
        asin_input.fill.assert_called_once_with(ASIN)
        page.get_by_role.return_value.first.click.assert_called_once()

    def test_unknown_identity_is_not_authenticated(self):
        with patch.object(collector, '_sellersprite_auth_state', return_value='unknown'):
            self.assertEqual(collector._sellersprite_login_block_reason(MagicMock(), MagicMock()), 'sellersprite_login_unverified')

    def test_late_result_survives_disappearing_loading_mask(self):
        page = FakePage(delay=2, response=Response({'items': [{'asin': ASIN}], 'total': 1}))
        rows, elapsed, reason = self.query(page, [{'asin': ASIN}])
        self.assertEqual(reason, 'matched')
        self.assertGreaterEqual(elapsed, 2000)
        self.assertEqual(rows[0]['asin'], ASIN)

    def test_stale_table_without_matching_response_is_not_success(self):
        _, _, reason = self.query(FakePage(), [{'asin': ASIN}])
        self.assertEqual(reason, 'query_timeout')

    def test_different_asin_response_cannot_confirm_empty(self):
        _, _, reason = self.query(FakePage(response=Response(asin='B0HBQ6N1ZC')))
        self.assertEqual(reason, 'query_timeout')

    def test_authenticated_successful_empty_is_confirmed(self):
        _, _, reason = self.query(FakePage(response=Response()))
        self.assertEqual(reason, 'confirmed_empty')

    def test_request_failure_is_not_not_found(self):
        for code, status, expected in [('ERROR', 200, 'query_api_error'), ('OK', 429, 'rate_limited'), ('OK', 401, 'authentication_or_permission_required')]:
            with self.subTest(status=status, code=code):
                _, _, reason = self.query(FakePage(response=Response(code=code, status=status)))
                self.assertEqual(reason, expected)

    def test_api_success_with_unrelated_asins_is_result_mismatch(self):
        page = FakePage(response=Response({'items': [{'asin': 'B001NCAP2C'}], 'total': 1}))
        _, _, reason = self.query(page)
        self.assertEqual(reason, 'query_result_mismatch')

    def test_data_present_but_parser_empty_is_parse_error(self):
        _, _, reason = self.query(FakePage(response=Response({'items': [{'asin': ASIN}], 'total': 1})))
        self.assertEqual(reason, 'query_parse_error')

    def test_expired_session_stops_query(self):
        _, _, reason = self.query(FakePage(response=Response()), state='guest')
        self.assertEqual(reason, 'sellersprite_login_required')

    def test_only_recent_verified_empty_can_be_cached(self):
        outcome = {'status': 'not_found', 'stop_reason': 'confirmed_empty', 'empty_verified': True, 'auth_verified': True, 'observed_at': datetime.now(timezone.utc).isoformat()}
        self.assertTrue(run._cacheable_empty(outcome))
        self.assertFalse(run._cacheable_empty({**outcome, 'auth_verified': False}))
        self.assertFalse(run._cacheable_empty({**outcome, 'observed_at': (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}))
        self.assertFalse(run._cacheable_empty({'status': 'not_found_or_unavailable'}))

    def test_legacy_bad_cache_is_queried_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'05-sellersprite-de-raw.json').write_text(json.dumps({'records': [], 'outcomes': [{'asin': ASIN, 'status': 'not_found_or_unavailable'}]}))
            with patch.object(run, 'collect_sellersprite_by_asin', return_value={'records': [], 'outcomes': [], 'collection_status': 'blocked', 'block_reason': 'sellersprite_login_required'}) as query:
                manifest = {'artifacts': {}, 'warnings': []}
                run._enrich_records_from_sellersprite([{'marketplace':'DE','asin':ASIN}], {}, root, manifest)
                query.assert_called_once()
                self.assertIn('sellersprite_login_required', manifest['enrichment_blocking_items'])

    def test_unsupported_batch_resets_page_before_single_queries(self):
        page = MagicMock()
        runtime = MagicMock()
        with patch.object(collector, '_require_playwright', return_value=runtime), \
             patch.object(collector, '_launch_context', return_value=(MagicMock(), page, Path('/tmp/profile'))), \
             patch.object(collector, '_sellersprite_credentials', return_value=('', '', None)), \
             patch.object(collector, '_wait_for_sellersprite_session', return_value=None), \
             patch.object(collector, '_select_sellersprite_market', return_value='德国站'), \
             patch.object(collector, '_goto') as navigate, \
             patch.object(collector, '_query_sellersprite_batch', return_value=([], 600, 'query_response_unrecognized')), \
             patch.object(collector, '_wait_sellersprite_query', side_effect=[([{'asin': ASIN}], 600, 'matched'), ([{'asin': 'B0HBQ6N1ZC'}], 600, 'matched')]):
            result = collector.collect_sellersprite_by_asin({'marketplace':'DE', 'asins':[ASIN, 'B0HBQ6N1ZC']})
            self.assertEqual(result['counts']['enriched'], 2)
            self.assertEqual(navigate.call_count, 2)
            self.assertTrue(all(row['status']=='enriched' for row in result['outcomes']))

    def test_unverified_login_cannot_start_product_queries(self):
        with patch.object(collector, '_require_playwright', return_value=MagicMock()), \
             patch.object(collector, '_launch_context', return_value=(MagicMock(), MagicMock(), Path('/tmp/profile'))), \
             patch.object(collector, '_sellersprite_credentials', return_value=('', '', None)), \
             patch.object(collector, '_wait_for_sellersprite_session', return_value='sellersprite_login_required'), \
             patch.object(collector, '_goto'), \
             patch.object(collector, '_wait_sellersprite_query') as query:
            result = collector.collect_sellersprite_by_asin({'marketplace':'DE','asins':[ASIN]})
            query.assert_not_called()
            self.assertEqual(result['collection_status'],'blocked')
            self.assertEqual(result['outcomes'][0]['status'],'blocked')

    def test_missing_fields_do_not_reject_a_product(self):
        candidate = pipeline.merge_candidates([{'marketplace': 'DE', 'asin': ASIN, 'new_release_rank': 1}])
        row = pipeline.score_candidates(candidate)['results'][0]
        self.assertEqual(row['conclusion'], '🟡 待补数据')
        self.assertEqual(row['score_status'], 'insufficient_data')

    def test_blocked_enrichment_does_not_export_workbook(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(run, 'collect_sellersprite_by_asin', return_value={'records': [], 'outcomes': [], 'collection_status':'blocked','block_reason':'query_api_error'}), patch.object(run, 'export_discovery_workbook') as export:
            result=run.run_discovery_flow({'request':'派对用品新品','run_dir':folder,'discovery_records':[{'marketplace':'DE','asin':ASIN,'new_release_rank':1}]})
            self.assertEqual(result['status'], 'AWAITING_ENRICHMENT')
            export.assert_not_called()

if __name__ == '__main__':
    unittest.main()


class EnvironmentCredentialsTests(unittest.TestCase):
    def test_complete_environment_is_used(self):
        with patch.dict(collector.os.environ, {"CHENYU_SELLERSPRITE_USERNAME": "test-account", "CHENYU_SELLERSPRITE_PASSWORD": "test-secret"}, clear=True):
            self.assertEqual(collector._sellersprite_credentials(), ("test-account", "test-secret", "environment"))

    def test_absent_environment_allows_existing_session(self):
        with patch.dict(collector.os.environ, {}, clear=True):
            self.assertEqual(collector._sellersprite_credentials(), ("", "", None))

    def test_incomplete_environment_fails_without_exposing_value(self):
        for env in ({"CHENYU_SELLERSPRITE_USERNAME": "test-account"}, {"CHENYU_SELLERSPRITE_PASSWORD": "test-secret"}):
            with self.subTest(keys=list(env)), patch.dict(collector.os.environ, env, clear=True):
                with self.assertRaises(collector.BrowserCollectionError) as raised:
                    collector._sellersprite_credentials()
                self.assertNotIn("test-secret", str(raised.exception))
                self.assertNotIn("test-account", str(raised.exception))


class PartialEnrichmentTests(unittest.TestCase):
    def test_one_result_mismatch_does_not_skip_other_asins(self):
        other = 'B0HBQ6N1ZC'
        page = MagicMock()
        with patch.object(collector, '_require_playwright', return_value=MagicMock()), \
             patch.object(collector, '_launch_context', return_value=(MagicMock(), page, Path('/tmp/profile'))), \
             patch.object(collector, '_sellersprite_credentials', return_value=('', '', None)), \
             patch.object(collector, '_wait_for_sellersprite_session', return_value=None), \
             patch.object(collector, '_select_sellersprite_market', return_value='德国站'), \
             patch.object(collector, '_goto'), \
             patch.object(collector, '_query_sellersprite_batch', return_value=([], 500, 'partial_match')), \
             patch.object(collector, '_wait_sellersprite_query', side_effect=[([], 500, 'query_result_mismatch'), ([], 500, 'query_result_mismatch'), ([{'asin': other}], 500, 'matched')]) as query:
            result = collector.collect_sellersprite_by_asin({'marketplace': 'DE', 'asins': [ASIN, other], 'query_delay_ms': 0})
        self.assertEqual(query.call_count, 3)
        self.assertEqual(result['collection_status'], 'partial')
        self.assertIsNone(result['block_reason'])
        self.assertEqual(result['counts']['enriched'], 1)
        self.assertEqual({row['asin'] for row in result['records']}, {other})
        self.assertEqual({(row['asin'], row['status']) for row in result['outcomes']}, {(ASIN, 'query_failed'), (other, 'enriched')})

    def test_partial_workbook_marks_unmatched_asin_and_resume_clears_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            requested = [
                {'marketplace': 'DE', 'asin': ASIN, 'new_release_rank': 2},
                {'marketplace': 'DE', 'asin': 'B0HBQ6N1ZC', 'new_release_rank': 3},
            ]
            def enriched(asin):
                return {'marketplace': 'DE', 'asin': asin, 'product_name': 'Fixture product',
                        'source_available_date': '2026-09-01', 'review_count': 5, 'price': 19.99,
                        'bsr': 100, 'category_name': 'Fixture', 'estimated_sales': 300}
            def first(_):
                return {'collection_status': 'partial', 'block_reason': None,
                        'records': [enriched(ASIN)],
                        'outcomes': [{'asin': ASIN, 'status': 'enriched', 'stop_reason': 'matched'},
                                     {'asin': 'B0HBQ6N1ZC', 'status': 'query_failed', 'stop_reason': 'query_result_mismatch'}]}
            args = {'request': 'fixture', 'run_dir': str(root), 'output_path': str(root / '开品结果.xlsx'),
                    'discovery_records': requested, 'as_of_date': '2026-09-24'}
            with patch.object(run, 'collect_sellersprite_by_asin', side_effect=first):
                partial = run.run_discovery_flow(args)
            self.assertEqual(partial['status'], 'PARTIAL')
            self.assertTrue(Path(partial['workbook']['path']).is_file())
            screening = json.loads((root / '09-screening.json').read_text(encoding='utf-8'))
            self.assertEqual(len(screening['results']), 2)
            def second(_):
                return {'collection_status': 'complete', 'block_reason': None,
                        'records': [enriched('B0HBQ6N1ZC')],
                        'outcomes': [{'asin': 'B0HBQ6N1ZC', 'status': 'enriched', 'stop_reason': 'matched'}]}
            with patch.object(run, 'collect_sellersprite_by_asin', side_effect=second):
                completed = run.run_discovery_flow(args)
            self.assertEqual(completed['status'], 'COMPLETE')
            self.assertFalse(json.loads((root / '00-run.json').read_text(encoding='utf-8')).get('enrichment_incomplete'))
