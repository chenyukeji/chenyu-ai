"""Behavioral coverage for shared browser ownership and login throttling."""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/chenyu-kaifa/skills/chenyu-xuanpin/scripts'
SPEC = importlib.util.spec_from_file_location('shared_session_test_module', SCRIPTS / 'sellersprite_session.py')
ss = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ss)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('CHENYU_BROWSER_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('CHENYU_SELLERSPRITE_ENTRY_CONFIG', str(tmp_path / 'entry.json'))
    (tmp_path / 'entry.json').write_text(json.dumps({'version': 1, 'browser_data_dir': str(tmp_path)}))
    monkeypatch.setenv('CHENYU_SELLERSPRITE_USERNAME', 'test-account')
    return ss.SessionStore()


def fake_page(store, browser_state=None, outcome='success'):
    state = browser_state if browser_state is not None else {'authenticated': False, 'submits': 0}
    context = SimpleNamespace(_chenyu_sellersprite_store=store,
                              _chenyu_sellersprite_session_path=store.state,
                              _chenyu_sellersprite_account=store.account,
                              cookies=lambda: [{'name': 'session', 'value': 'test',
                                                'domain': '.sellersprite.com', 'path': '/'}])
    page = MagicMock()
    page.context = context
    page.url = 'about:blank'
    page.error = None
    page.state = state
    page.goto.side_effect = lambda url, **kw: setattr(page, 'url', url)
    page.is_closed.return_value = False
    page.locator.return_value.first.is_disabled.return_value = False

    def submit():
        state['submits'] += 1
        if outcome == 'success':
            state['authenticated'] = True
            page.url = ss.DEFAULT_URL
        elif outcome == 'exception':
            raise RuntimeError('sensitive-password-in-browser-trace')
        else:
            page.error = outcome
    page.get_by_role.return_value.first.click.side_effect = submit
    return page


@pytest.fixture
def fake_identity(monkeypatch):
    monkeypatch.setattr(ss, 'wait_identity', lambda p: 'authenticated' if p.state['authenticated'] else 'guest')
    monkeypatch.setattr(ss, 'auth_state', lambda p: 'authenticated' if p.state['authenticated'] else 'guest')
    monkeypatch.setattr(ss, 'page_block_reason', lambda p: p.error)


def test_independent_plugins_bundle_same_session_contract():
    other = ROOT / 'plugins/chenyu-yunying/skills/chenyu-listing/scripts/sellersprite_session.py'
    assert other.read_bytes() == (SCRIPTS / 'sellersprite_session.py').read_bytes()


def test_paths_stable_across_task_directories_and_separate_accounts(store, tmp_path, monkeypatch):
    first = store.root
    monkeypatch.chdir(tmp_path)
    assert ss.SessionStore().root == first
    assert ss.SessionStore('different-account').root != first


def test_verified_session_never_submits_password(store, fake_identity):
    page = fake_page(store, {'authenticated': True, 'submits': 0})
    result = ss.ensure_login(page, store.account, 'test-secret')
    assert result == {'login_status': 'verified', 'session_reused': True}
    assert page.state['submits'] == 0
    assert store.state.stat().st_mode & 0o777 == 0o600
    assert 'test-secret' not in store.state.read_text()


def test_first_login_is_reused_by_next_window(store, fake_identity):
    shared = {'authenticated': False, 'submits': 0}
    first = ss.ensure_login(fake_page(store, shared), store.account, 'secret')
    second = ss.ensure_login(fake_page(ss.SessionStore(), shared), store.account, 'secret')
    assert first['session_reused'] is False
    assert second['session_reused'] is True
    assert shared['submits'] == 1


def test_two_waiting_windows_only_submit_once(store, fake_identity):
    shared = {'authenticated': False, 'submits': 0}
    results = []
    threads = [threading.Thread(target=lambda: results.append(
        ss.ensure_login(fake_page(ss.SessionStore(), shared), store.account, 'secret')))
        for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(results) == 2
    assert all(r['login_status'] == 'verified' for r in results)
    assert shared['submits'] == 1


@pytest.mark.parametrize('reason', sorted(ss.HARD_BLOCKS))
def test_fatal_failure_blocks_future_tasks_until_explicit_recovery(store, fake_identity, reason):
    first = fake_page(store, outcome=reason)
    assert ss.ensure_login(first, store.account, 'secret')['block_reason'] == reason
    another = fake_page(ss.SessionStore())
    assert ss.ensure_login(another, store.account, 'secret')['block_reason'] == reason
    assert another.state['submits'] == 0
    assert ss.ensure_login(another, store.account, 'secret', recover=True)['login_status'] == 'verified'
    assert another.state['submits'] == 1


def test_unknown_failure_cools_down_without_leaking_password(store, fake_identity):
    page = fake_page(store, outcome='exception')
    result = ss.ensure_login(page, store.account, 'sensitive-password-in-browser-trace')
    assert result['block_reason'] == 'sellersprite_login_navigation_failed'
    assert 'sensitive-password' not in json.dumps(result) + store.guard.read_text()
    next_page = fake_page(ss.SessionStore())
    assert ss.ensure_login(next_page, store.account, 'secret')['block_reason'] == 'sellersprite_login_cooldown'
    assert next_page.state['submits'] == 0


def test_network_error_does_not_erase_account_lock(store, fake_identity):
    store.failed('sellersprite_account_locked')
    page = fake_page(store)
    page.goto.side_effect = RuntimeError('network unavailable')
    assert ss.ensure_login(page, store.account, 'secret')['block_reason'] == 'sellersprite_account_locked'
    assert store.blocked_reason() == 'sellersprite_account_locked'


def test_status_never_attempts_login(store, fake_identity):
    page = fake_page(store)
    assert ss.ensure_login(page, store.account, 'secret', check_only=True)['login_status'] == 'blocked'
    assert page.state['submits'] == 0


def test_corrupt_guard_fails_closed(store, fake_identity):
    store.root.mkdir(parents=True)
    store.guard.write_text('broken')
    page = fake_page(store)
    assert ss.ensure_login(page, store.account, 'secret')['block_reason'] == 'sellersprite_login_guard_invalid'
    assert page.state['submits'] == 0


def test_verified_account_without_query_permission_does_not_relogin(store, fake_identity):
    page = fake_page(store, {'authenticated': True, 'submits': 0})
    page.locator.return_value.first.is_disabled.return_value = True
    assert ss.ensure_login(page, store.account, 'secret', require_asin_query=True)['block_reason'] == 'sellersprite_asin_query_unavailable'
    assert page.state['submits'] == 0


def test_window_close_never_closes_shared_context_or_browser():
    context, page, browser = MagicMock(), MagicMock(), MagicMock()
    page.is_closed.return_value = False
    owned = ss.ManagedContext(context, page, browser)
    owned.close()
    owned.close()
    page.close.assert_called_once()
    context.close.assert_not_called()
    browser.close.assert_not_called()


def test_login_mutex_blocks_another_process_and_releases(store):
    code = """import sys
sys.path.insert(0, sys.argv[1])
from sellersprite_session import SessionStore, SessionError
s = SessionStore()
try:
    s.acquire(0)
except SessionError:
    print('busy')
else:
    s.release()
    print('available')
"""
    store.acquire()
    try:
        result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS)], capture_output=True, text=True, check=True)
        assert result.stdout.strip() == 'busy'
    finally:
        store.release()
    result = subprocess.run([sys.executable, '-c', code, str(SCRIPTS)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'available'


@pytest.mark.parametrize('text,reason', [
    ('子账号被锁定，请联系主账号解锁哦！', 'sellersprite_account_locked'),
    ('账号或密码错误', 'invalid_credentials'),
    ('请完成安全验证', 'sellersprite_security_challenge_requires_user'),
    ('验证码登录 找回密码', None),
])
def test_page_failure_classification(text, reason):
    page = MagicMock()
    page.locator.return_value.inner_text.return_value = text
    page.locator.return_value.count.return_value = 0
    assert ss.page_block_reason(page) == reason


@pytest.mark.skipif(os.environ.get('CHENYU_BROWSER_SMOKE') != '1', reason='opt-in real Chromium check')
def test_real_browser_windows_and_driver_disconnect_share_cookies(store):
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as runtime:
            first, a, _ = ss.launch_context(runtime, {})
            browser_pid = ss.read_json(store.root / 'browser-process.json')['pid']
            if os.name != 'nt':
                assert (Path('/proc') / str(browser_pid) / 'cwd').resolve() == store.root
            first.add_cookies([{'name': 'shared-test', 'value': 'same-browser',
                               'domain': 'www.sellersprite.com', 'path': '/'}])
            a.goto('data:text/html,<title>First window</title>')
            with pytest.raises(ss.SessionError, match='sellersprite_session_busy'):
                ss.launch_context(runtime, {'session_wait_seconds': 0})
            assert a.title() == 'First window'
            first.close()
            second, b, _ = ss.launch_context(runtime, {})
            b.goto('data:text/html,<title>Second window</title>')
            assert any(c['name'] == 'shared-test' for c in second.cookies())
            assert b.title() == 'Second window'
            second.close()
            assert ss.browser_endpoint(store) is not None
            assert store.state.exists()
        with sync_playwright() as runtime:
            third, c, _ = ss.launch_context(runtime, {})
            assert ss.read_json(store.root / 'browser-process.json')['pid'] == browser_pid
            assert any(x['name'] == 'shared-test' for x in third.cookies())
            third.close()
            assert ss.browser_endpoint(store) is not None
    finally:
        data = ss.read_json(store.root / 'browser-process.json')
        if data.get('pid'):
            try:
                os.kill(data['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize('authenticated', [True, False])
def test_saved_lock_stops_before_any_navigation(store, fake_identity, authenticated):
    store.failed('sellersprite_account_locked')
    page = fake_page(store, {'authenticated': authenticated, 'submits': 0})
    result = ss.ensure_login(page, store.account, 'secret')
    assert result['block_reason'] == 'sellersprite_account_locked'
    page.goto.assert_not_called()
    assert store.blocked_reason() == 'sellersprite_account_locked'
    with pytest.raises(ss.SessionError, match='sellersprite_account_locked'):
        store.verified()


def test_logged_in_header_cannot_hide_page_lock(store, fake_identity):
    page = fake_page(store, {'authenticated': True, 'submits': 0})
    page.error = 'sellersprite_account_locked'
    assert ss.ensure_login(page, store.account, 'secret')['block_reason'] == page.error
    assert ss.SessionStore().blocked_reason() == page.error


def test_host_entry_overrides_missing_or_conflicting_task_env(store, monkeypatch, tmp_path):
    expected = store.root
    monkeypatch.delenv('CHENYU_BROWSER_DATA_DIR')
    assert ss.SessionStore().root == expected
    monkeypatch.setenv('CHENYU_BROWSER_DATA_DIR', str(tmp_path / 'independent'))
    assert ss.SessionStore().root == expected
    Path(os.environ['CHENYU_SELLERSPRITE_ENTRY_CONFIG']).write_text('broken')
    with pytest.raises(ss.SessionError, match='sellersprite_entry_config_invalid'):
        ss.SessionStore()


def test_lock_prevents_browser_start_and_survives_expired_cooldown(store):
    ss.private_write(store.guard, {'block_reason': 'sellersprite_account_locked', 'retry_after': 0})
    runtime = MagicMock()
    with pytest.raises(ss.SessionError, match='sellersprite_account_locked'):
        ss.launch_context(runtime, {})
    runtime.chromium.connect_over_cdp.assert_not_called()


def test_operation_lease_covers_queries_after_login_lock_released(store):
    store.acquire_operation(0)
    store.acquire()
    store.release()
    other = ss.SessionStore()
    try:
        with pytest.raises(ss.SessionError, match='sellersprite_session_busy'):
            other.acquire_operation(0)
    finally:
        store.release_operation()
    other.acquire_operation(0)
    other.release_operation()


def test_waiter_stops_when_other_collector_reports_lock(store):
    store.acquire_operation(0)
    outcome = []
    ready = threading.Event()
    def wait():
        ready.set()
        try:
            ss.SessionStore().acquire_operation(3)
        except ss.SessionError as exc:
            outcome.append(str(exc))
    thread = threading.Thread(target=wait)
    thread.start()
    ready.wait(1)
    store.failed('sellersprite_account_locked')
    thread.join(2)
    store.release_operation()
    assert not thread.is_alive()
    assert outcome == ['sellersprite_account_locked']


def test_browser_start_exception_releases_operation_lease(store, monkeypatch):
    monkeypatch.setattr(ss, 'start_browser', MagicMock(side_effect=RuntimeError('launch failed')))
    with pytest.raises(RuntimeError, match='launch failed'):
        ss.launch_context(MagicMock(), {})
    other = ss.SessionStore()
    other.acquire_operation(0)
    other.release_operation()


def test_request_guard_blocks_next_business_request_and_429_cools_all_tasks(store):
    page = MagicMock()
    ss.install_guard(page, store)
    events = {call.args[0]: call.args[1] for call in page.on.call_args_list}
    response = SimpleNamespace(url=ss.DEFAULT_URL, status=429,
                               request=SimpleNamespace(resource_type='xhr'))
    events['response'](response)
    route = MagicMock()
    route.request.url = 'https://www.sellersprite.com/v3/api/relation/reversing'
    page.route.call_args.args[1](route)
    route.abort.assert_called_once()
    route.continue_.assert_not_called()
    assert ss.SessionStore().operation_block() == 'sellersprite_login_cooldown'
    ss.private_write(store.guard, {'block_reason': 'sellersprite_rate_limited', 'retry_after': 0})
    assert store.operation_block() is None


def test_async_page_lock_publishes_to_other_plugin_processes(store):
    page = MagicMock()
    ss.install_guard(page, store)
    callback = page.expose_binding.call_args.args[1]
    callback({'frame': SimpleNamespace(url=ss.DEFAULT_URL)}, 'sellersprite_account_locked')
    assert ss.SessionStore().operation_block() == 'sellersprite_account_locked'


def test_failed_recovery_keeps_original_hard_block(store, fake_identity):
    store.failed('sellersprite_account_locked')
    page = fake_page(store, outcome='exception')
    assert ss.ensure_login(page, store.account, 'secret', recover=True)['block_reason'] == 'sellersprite_account_locked'
    assert ss.SessionStore().operation_block() == 'sellersprite_account_locked'


def test_guest_401_can_login_but_authenticated_401_stops_everyone(store):
    page = MagicMock()
    ss.install_guard(page, store)
    callback = dict(call.args for call in page.on.call_args_list)['response']
    response = SimpleNamespace(url=ss.DEFAULT_URL, status=401,
                               request=SimpleNamespace(resource_type='xhr'))
    callback(response)
    assert store.operation_block() is None
    store.authenticated = True
    callback(response)
    assert ss.SessionStore().operation_block() == 'sellersprite_session_lost'


def test_last_task_keeps_browser_running_and_releases_lease(store, fake_identity):
    store.acquire_operation(0)
    page = fake_page(store)
    browser = MagicMock()
    managed = ss.ManagedContext(page.context, page, browser)
    managed.close()
    managed.close()
    page.close.assert_called_once()
    browser.close.assert_not_called()
    browser.new_browser_cdp_session.assert_not_called()
    other = ss.SessionStore()
    other.acquire_operation(0)
    other.release_operation()
    assert store.state.exists()
