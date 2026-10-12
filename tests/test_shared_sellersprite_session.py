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
            first.add_cookies([{'name': 'shared-test', 'value': 'same-browser',
                               'domain': 'www.sellersprite.com', 'path': '/'}])
            a.goto('data:text/html,<title>First window</title>')
            second, b, _ = ss.launch_context(runtime, {})
            b.goto('data:text/html,<title>Second window</title>')
            assert a.title() == 'First window'
            assert any(c['name'] == 'shared-test' for c in second.cookies())
            first.close()
            assert ss.browser_endpoint(store) is not None
            assert b.title() == 'Second window'
            second.close()
            assert ss.browser_endpoint(store) is None
            assert store.state.exists()
        with sync_playwright() as runtime:
            third, c, _ = ss.launch_context(runtime, {})
            assert any(x['name'] == 'shared-test' for x in third.cookies())
            third.close()
            assert ss.browser_endpoint(store) is None
    finally:
        data = ss.read_json(store.root / 'browser-process.json')
        if data.get('pid'):
            try:
                os.kill(data['pid'], signal.SIGTERM)
            except ProcessLookupError:
                pass
