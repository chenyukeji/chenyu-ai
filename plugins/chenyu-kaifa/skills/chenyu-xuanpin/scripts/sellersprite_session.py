"""Shared SellerSprite session contract, bundled identically in both plugins.

One account lease covers browser startup, login, queries and cleanup.
Website and manual collectors resolve the same host entry configuration.
The browser stays running between tasks; only task-owned windows are closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

LOGIN_URL = 'https://www.sellersprite.com/cn/w/user/login'
DEFAULT_URL = 'https://www.sellersprite.com/v3/competitor-lookup'
COOLDOWN_SECONDS = 300
HARD_BLOCKS = {'sellersprite_account_locked', 'invalid_credentials',
               'sellersprite_security_challenge_requires_user', 'sellersprite_session_lost',
               'sellersprite_access_denied'}


class SessionError(ValueError):
    pass


def seller_url(url):
    parsed = urlparse(str(url))
    host = (parsed.hostname or '').lower()
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (host == 'sellersprite.com' or host.endswith('.sellersprite.com'))):
        raise SessionError('sellersprite_url_required')
    return str(url)


def base_dir():
    # The website registers one host entry. A missing task env must never fork it.
    entry = Path(os.environ.get('CHENYU_SELLERSPRITE_ENTRY_CONFIG',
                                Path.home() / '.config/chenyu/sellersprite-entry.json')).expanduser()
    if entry.exists() or 'CHENYU_SELLERSPRITE_ENTRY_CONFIG' in os.environ:
        config = read_json(entry)
        value = config.get('browser_data_dir')
        if config.get('version') != 1 or not isinstance(value, str) or not Path(value).is_absolute():
            raise SessionError('sellersprite_entry_config_invalid')
        return Path(value).resolve()
    configured = os.environ.get('CHENYU_BROWSER_DATA_DIR')
    return (Path(configured).expanduser() if configured else
            Path.home() / '.local/share/chenyu/browser-profiles').resolve()


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.session-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def seller_cookie(cookie):
    if not isinstance(cookie, dict):
        return False
    domain = str(cookie.get('domain', '')).lstrip('.').lower()
    return domain == 'sellersprite.com' or domain.endswith('.sellersprite.com')


def restore_session(context, path, account=None):
    account = os.environ.get('CHENYU_SELLERSPRITE_USERNAME', '').strip() if account is None else account
    state = read_json(path)
    if state.get('account') != account:
        return False
    try:
        cookies = [c for c in state.get('cookies', []) if seller_cookie(c)
                   and (c.get('expires', -1) <= 0 or c['expires'] > time.time())]
        if cookies:
            context.add_cookies(cookies)
            return True
    except (TypeError, ValueError, KeyError):
        pass
    return False


def save_session(context):
    path = getattr(context, '_chenyu_sellersprite_session_path', None)
    if isinstance(path, Path):
        account = getattr(context, '_chenyu_sellersprite_account', None)
        if not isinstance(account, str):
            account = os.environ.get('CHENYU_SELLERSPRITE_USERNAME', '').strip()
        private_write(path, {'account': account,
                            'cookies': [c for c in context.cookies() if seller_cookie(c)]})


class SessionStore:
    def __init__(self, account=None):
        self.account = os.environ.get('CHENYU_SELLERSPRITE_USERNAME', '').strip() if account is None else account
        key = hashlib.sha256(self.account.encode()).hexdigest()[:24]
        self.root = base_dir() / 'sellersprite/accounts' / key
        self.profile = self.root / 'browser'
        self.state = self.root / 'sellersprite-session.json'
        self.guard = self.root / 'login-guard.json'
        self.lock = None
        self.operation_lock = None
        self.recovering = False
        self.recovery_failed = False
        self.authenticated = False

    def acquire_operation(self, timeout=1200, *, recover=False):
        # Separate from the short login/startup lock for backwards compatibility.
        self.recovering = recover
        self._check_operation()
        lease = SessionStore(self.account)
        lease.root = self.root
        lease.acquire(timeout, name='operation.lock', check=self._check_operation)
        self.operation_lock = lease
        try:
            self._check_operation()
        except BaseException:
            self.release_operation()
            raise

    def release_operation(self):
        if self.operation_lock is not None:
            self.operation_lock.release()
            self.operation_lock = None

    def operation_block(self):
        reason = self.blocked_reason()
        if self.recovering and not self.recovery_failed:
            return None
        if reason in HARD_BLOCKS or reason == 'sellersprite_login_guard_invalid':
            return reason
        guard = read_json(self.guard)
        if reason and guard.get('block_reason') not in (None, 'sellersprite_login_in_progress'):
            return reason
        return None

    def _check_operation(self):
        if reason := self.operation_block():
            raise SessionError(reason)

    def acquire(self, timeout=180, *, name='session.lock', check=None):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        path = self.root / name
        self.lock = path.open('a+b')
        path.chmod(0o600)
        self.lock.seek(0)
        self.lock.write(b'0')
        self.lock.flush()
        deadline = time.monotonic() + timeout
        try:
            while True:
                if check:
                    check()
                try:
                    if os.name == 'nt':
                        import msvcrt
                        self.lock.seek(0)
                        msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise SessionError('sellersprite_session_busy')
                    time.sleep(0.2)
        except BaseException:
            self.lock.close()
            self.lock = None
            raise

    def release(self):
        if self.lock is not None:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            self.lock.close()
            self.lock = None

    def blocked_reason(self):
        if not self.guard.exists():
            return None
        guard = read_json(self.guard)
        if not guard:
            return 'sellersprite_login_guard_invalid'
        reason = guard.get('block_reason')
        if reason in HARD_BLOCKS:
            return reason
        try:
            if float(guard.get('retry_after', 0)) > time.time():
                return 'sellersprite_login_cooldown'
        except (TypeError, ValueError):
            return 'sellersprite_login_guard_invalid'
        return None

    def attempted(self):
        if read_json(self.guard).get('block_reason') in HARD_BLOCKS:
            return
        private_write(self.guard, {'block_reason': 'sellersprite_login_in_progress',
                                  'retry_after': time.time() + COOLDOWN_SECONDS})

    def failed(self, reason, *, cooldown=COOLDOWN_SECONDS):
        self.recovery_failed = True
        previous = read_json(self.guard).get('block_reason')
        if previous in HARD_BLOCKS:
            return previous
        private_write(self.guard, {'block_reason': reason,
                                  'retry_after': time.time() + cooldown})
        return reason

    def verified(self, *, recover=False):
        if not recover and self.operation_block():
            raise SessionError(self.operation_block())
        # Retain the last login's cooldown if the session immediately disappears.
        guard = read_json(self.guard)
        private_write(self.guard, {'block_reason': None,
                                  'retry_after': guard.get('retry_after', 0)})


class ManagedContext:
    """Close only this task window and keep the account browser running."""
    def __init__(self, context, page, browser):
        self.context, self.page, self.browser = context, page, browser
        self.closed = False

    def __getattr__(self, name):
        return getattr(self.context, name)

    def close(self):
        if self.closed:
            return
        store = getattr(self.context, '_chenyu_sellersprite_store', None)
        if not isinstance(store, SessionStore):
            if not self.page.is_closed():
                self.page.close()
            self.closed = True
            return
        try:
            store.acquire()
            try:
                if not self.page.is_closed():
                    observe_page(self.page)
                    self.page.close()
                self.closed = True
                save_session(self.context)
            finally:
                store.release()
        finally:
            store.release_operation()


def browser_endpoint(store):
    try:
        lines = (store.profile / 'DevToolsActivePort').read_text().splitlines()
        port = int(lines[0])
        if not 1 <= port <= 65535 or not lines[1].startswith('/devtools/browser/'):
            return None
        endpoint = f'http://127.0.0.1:{port}'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(endpoint + '/json/version', timeout=1) as response:
            version = json.load(response)
        websocket = version.get('webSocketDebuggerUrl', '')
        if urlparse(websocket).path == lines[1]:
            return endpoint
    except (OSError, ValueError, IndexError):
        pass
    return None


def start_browser(runtime, store, headless=True):
    if endpoint := browser_endpoint(store):
        return endpoint, False
    store.profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = {key: value for key, value in os.environ.items()
                   if key not in {'CHENYU_SELLERSPRITE_USERNAME', 'CHENYU_SELLERSPRITE_PASSWORD'}}
    command = [runtime.chromium.executable_path, f'--user-data-dir={store.profile}',
               '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
               '--no-first-run', '--no-default-browser-check', '--disable-dev-shm-usage',
               '--disable-background-networking', '--disable-component-update',
               '--disable-popup-blocking', '--no-sandbox']
    if headless:
        command.append('--headless=new')
    command.append('about:blank')
    options = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env=environment, cwd=store.root, **options)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if endpoint := browser_endpoint(store):
            private_write(store.root / 'browser-process.json', {'pid': process.pid})
            return endpoint, True
        if process.poll() is not None:
            break
        time.sleep(0.2)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    raise SessionError('sellersprite_browser_start_failed')


def launch_context(runtime, payload):
    """Acquire the account queue and open one window in its persistent browser."""
    store = SessionStore()
    store.acquire_operation(max(0, min(float(payload.get('session_wait_seconds', 1200)), 1200)),
                            recover=payload.get('recover') is True)
    try:
        store.acquire()
        endpoint, started = start_browser(runtime, store, bool(payload.get('headless', True)))
        browser = runtime.chromium.connect_over_cdp(endpoint)
        context = browser.contexts[0]
        context._chenyu_sellersprite_store = store
        context._chenyu_sellersprite_account = store.account
        context._chenyu_sellersprite_session_path = store.state
        if started:
            cdp = browser.new_browser_cdp_session()
            try:
                seeds = [t['targetId'] for t in cdp.send('Target.getTargets')['targetInfos']
                         if t['type'] == 'page' and t.get('url') == 'about:blank']
                state = read_json(store.root / 'browser-process.json')
                private_write(store.root / 'browser-process.json', {**state, 'seed_targets': seeds})
            finally:
                cdp.detach()
            candidates = [store.state]
            legacy = [base_dir() / name / 'sellersprite-session.json' for name in ('browser', 'sellersprite')]
            candidates += sorted((p for p in legacy if p.exists()), key=lambda p: p.stat().st_mtime, reverse=True)
            for path in candidates:
                if restore_session(context, path, store.account):
                    break
        # A crashed/legacy caller may still own a live page despite the new lease.
        # Do not open a concurrent window or kill that caller's browser.
        channel = browser.new_browser_cdp_session()
        try:
            seeds = set(read_json(store.root / 'browser-process.json').get('seed_targets', []))
            if any(t['type'] == 'page' and (t['targetId'] not in seeds or t.get('url') != 'about:blank')
                   for t in channel.send('Target.getTargets')['targetInfos']):
                raise SessionError('sellersprite_browser_in_use')
        finally:
            channel.detach()
        managed, page, profile = _create_task_window(browser, context, store, payload)
        try:
            install_guard(page, store)
        except BaseException:
            page.close()
            raise
        return managed, page, profile
    except BaseException:
        store.release_operation()
        raise
    finally:
        store.release()


def _create_task_window(browser, context, store, payload):
    cdp = browser.new_browser_cdp_session()
    target = None
    try:
        target = cdp.send('Target.createTarget', {
            'url': 'about:blank', 'newWindow': True, 'background': True})['targetId']
        page = None
        deadline = time.monotonic() + 10
        while page is None and time.monotonic() < deadline:
            for candidate in context.pages:
                channel = None
                try:
                    channel = context.new_cdp_session(candidate)
                    info = channel.send('Target.getTargetInfo')['targetInfo']
                    if info['targetId'] == target:
                        page = candidate
                        break
                except Exception:
                    continue
                finally:
                    if channel is not None:
                        channel.detach()
            if page is None:
                # A protocol round trip also delivers pending page events.
                cdp.send('Target.getTargets')
                time.sleep(0.05)
        if page is None:
            raise SessionError('sellersprite_task_window_unavailable')
    except BaseException:
        if target:
            cdp.send('Target.closeTarget', {'targetId': target})
        raise
    finally:
        cdp.detach()
    page.set_default_timeout(int(payload.get('action_timeout_ms', 10000)))
    page.set_default_navigation_timeout(int(payload.get('navigation_timeout_ms', 30000)))
    page.set_viewport_size({'width': max(800, min(int(payload.get('viewport_width', 1440)), 2560)),
                            'height': max(600, min(int(payload.get('viewport_height', 1000)), 1600))})
    return ManagedContext(context, page, browser), page, store.profile


def observe_page(page):
    store = getattr(page.context, '_chenyu_sellersprite_store', None)
    reason = page_block_reason(page)
    if reason and isinstance(store, SessionStore):
        store.failed(reason)
    return reason


def assert_access(page):
    store = getattr(page.context, '_chenyu_sellersprite_store', None)
    if not isinstance(store, SessionStore):
        raise SessionError('sellersprite_shared_context_required')
    observe_page(page)
    store._check_operation()


def install_guard(page, store):
    def gate(route):
        host = (urlparse(route.request.url).hostname or '').lower()
        if (host == 'sellersprite.com' or host.endswith('.sellersprite.com')) and store.operation_block():
            route.abort('blockedbyclient')
        else:
            route.continue_()

    def response_status(response):
        host = (urlparse(response.url).hostname or '').lower()
        if not (host == 'sellersprite.com' or host.endswith('.sellersprite.com')):
            return
        if response.request.resource_type not in ('document', 'xhr', 'fetch'):
            return
        reasons = {429: 'sellersprite_rate_limited', 401: 'sellersprite_session_lost',
                   403: 'sellersprite_access_denied'}
        if response.status == 401 and not store.authenticated:
            return  # guest identity probes during initial login are expected
        if response.status in reasons:
            cooldown = COOLDOWN_SECONDS
            if response.status == 429:
                value = (getattr(response, 'headers', {}) or {}).get('retry-after', '')
                try:
                    from email.utils import parsedate_to_datetime
                    delay = int(value) if str(value).isdigit() else parsedate_to_datetime(value).timestamp() - time.time()
                    cooldown = max(cooldown, delay)
                except (ValueError, TypeError, AttributeError, OverflowError):
                    pass
            store.failed(reasons[response.status], cooldown=cooldown)

    def report(source, reason):
        host = (urlparse(source['frame'].url).hostname or '').lower()
        if (host == 'sellersprite.com' or host.endswith('.sellersprite.com')) and reason in HARD_BLOCKS:
            store.failed(reason)

    page.route('**/*', gate)
    page.on('response', response_status)
    page.expose_binding('__chenyuSellerBlock', report)
    # Observe asynchronous toast/dialog errors, including an already logged-in header.
    page.add_init_script(r"""(() => {
      if (!(location.hostname === 'sellersprite.com' || location.hostname.endsWith('.sellersprite.com'))) return;
      let sent = '', pending = false;
      const check = () => {
        pending = false;
        const text = document.body?.innerText || '';
        let reason = '';
        if (/子账[号户].*锁定|账号被锁|account.{0,30}locked/i.test(text)) reason = 'sellersprite_account_locked';
        else if (/账号或密码错误|用户名或密码错误|密码错误|incorrect password|invalid credentials/i.test(text)) reason = 'invalid_credentials';
        else if (/请输入验证码|请完成安全验证|向右滑动完成验证|人机验证|robot check/i.test(text)
          || [...document.querySelectorAll("input[name='captcha'], iframe[src*='captcha']")].some(el => el.getClientRects().length)) reason = 'sellersprite_security_challenge_requires_user';
        if (reason && reason !== sent) { sent = reason; window.__chenyuSellerBlock(reason).catch(() => {}); }
      };
      new MutationObserver(() => { if (!pending) { pending = true; setTimeout(check, 50); } })
        .observe(document, {subtree: true, childList: true, characterData: true, attributes: true});
      document.addEventListener('DOMContentLoaded', check);
    })();""")


def auth_state(page):
    try:
        seller_url(page.url)
        if observe_page(page):
            return 'blocked'
        store = getattr(page.context, '_chenyu_sellersprite_store', None)
        if isinstance(store, SessionStore) and store.operation_block():
            return 'blocked'
        identity = page.locator('.profile-trigger:visible').first
        if identity.count():
            label = identity.inner_text(timeout=1000).strip()
            if re.search(r'未登录|游客|登录/注册|sign in|log in', label, re.I):
                return 'guest'
            if label:
                if isinstance(store, SessionStore):
                    store.authenticated = True
                return 'authenticated'
        body = page.locator('body').inner_text(timeout=1000)
        if re.search(r'未登录|您是游客身份|登录/注册', body):
            return 'guest'
        if page.locator("input[type='password']:visible").count():
            return 'guest'
    except Exception:
        pass
    return 'unknown'


def page_block_reason(page):
    try:
        body = page.locator('body').inner_text(timeout=1000)
        if re.search(r'子账号.*锁定|子账户.*锁定|账号被锁|account.{0,30}locked', body, re.I):
            return 'sellersprite_account_locked'
        if re.search(r'账号或密码错误|用户名或密码错误|密码错误|incorrect password|invalid credentials', body, re.I):
            return 'invalid_credentials'
        if re.search(r'请输入验证码|请完成安全验证|向右滑动完成验证|人机验证|robot check', body, re.I):
            return 'sellersprite_security_challenge_requires_user'
        for selector in ("input[name='captcha']:visible", "iframe[src*='captcha']:visible"):
            if page.locator(selector).count():
                return 'sellersprite_security_challenge_requires_user'
    except Exception:
        pass
    return None


def wait_identity(page, timeout_ms=12000):
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        state = auth_state(page)
        if state != 'unknown' or page_block_reason(page) or time.monotonic() >= deadline:
            return state
        page.wait_for_timeout(200)


def _ensure_login_locked(page, username, password, destination=DEFAULT_URL, timeout_seconds=30,
                 *, require_asin_query=False, recover=False, check_only=False):
    destination = seller_url(destination)
    store = getattr(page.context, '_chenyu_sellersprite_store', None)
    if not isinstance(store, SessionStore) or store.account != username:
        raise SessionError('sellersprite_shared_context_required')

    def blocked(reason, persist=True):
        if persist:
            reason = store.failed(reason)
        return {'login_status': 'blocked', 'block_reason': reason}

    def verified(reused):
        if reason := page_block_reason(page):
            return blocked(reason)
        if not recover and (reason := store.operation_block()):
            return blocked(reason, False)
        if store.recovery_failed:
            return blocked(store.blocked_reason() or 'sellersprite_login_unverified', False)
        save_session(page.context)
        store.verified(recover=recover)
        store.authenticated = True
        if require_asin_query:
            field = page.locator("input[placeholder*='ASIN' i]:visible").first
            try:
                field.wait_for(state='visible', timeout=12000)
                if field.is_disabled():
                    return blocked('sellersprite_asin_query_unavailable', False)
            except Exception:
                return blocked('sellersprite_asin_query_unavailable', False)
        return {'login_status': 'verified', 'session_reused': reused}

    try:
        # Persisted hard blocks win over stale headers and precede every navigation.
        store.recovering = recover
        store.recovery_failed = False
        if not recover and (reason := store.operation_block()):
            return blocked(reason, False)
        page.goto(destination, wait_until='domcontentloaded')
        identity = wait_identity(page)
        if reason := page_block_reason(page):
            return blocked(reason)
        if identity == 'authenticated':
            return verified(True)
        if check_only:
            return blocked(store.blocked_reason() or 'sellersprite_login_required', False)
        if not recover and (reason := store.blocked_reason()):
            return blocked(reason, False)
        if not username or not password:
            return blocked('sellersprite_login_required', False)
        if identity != 'guest':
            return blocked('sellersprite_login_unverified')
        # Mark BEFORE navigation/submission so a killed worker cannot cause a login storm.
        store.attempted()
        page.goto(LOGIN_URL, wait_until='domcontentloaded')
        seller_url(page.url)
        if reason := page_block_reason(page):
            return blocked(reason)
        if auth_state(page) == 'authenticated':
            page.goto(destination, wait_until='domcontentloaded')
            return verified(True) if wait_identity(page) == 'authenticated' else blocked('sellersprite_login_unverified')
        page.locator("input[name='email']:visible").first.fill(username)
        page.locator("input[type='password']:visible").first.fill(password)
        page.get_by_role('button', name=re.compile(r'立即登录|log\s*in|sign\s*in', re.I)).first.click()
        deadline = time.monotonic() + max(1, min(timeout_seconds, 120))
        while time.monotonic() < deadline and not page.is_closed():
            if reason := page_block_reason(page):
                return blocked(reason)
            if '/user/login' not in page.url and '/user/signin' not in page.url:
                page.goto(destination, wait_until='domcontentloaded')
                if wait_identity(page) == 'authenticated':
                    return verified(False)
                return blocked(page_block_reason(page) or 'sellersprite_login_unverified')
            page.wait_for_timeout(300)
        return blocked('sellersprite_login_unverified')
    except Exception:
        # Never surface a Playwright trace containing filled credentials.
        return blocked('sellersprite_login_navigation_failed')


def ensure_login(page, username, password, destination=DEFAULT_URL, timeout_seconds=30,
                 *, require_asin_query=False, recover=False, check_only=False):
    store = getattr(page.context, '_chenyu_sellersprite_store', None)
    if not isinstance(store, SessionStore) or store.account != username:
        raise SessionError('sellersprite_shared_context_required')
    store.acquire()
    try:
        return _ensure_login_locked(page, username, password, destination, timeout_seconds,
                                    require_asin_query=require_asin_query,
                                    recover=recover, check_only=check_only)
    finally:
        store.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'login', 'recover'])
    args = parser.parse_args()
    user = os.environ.get('CHENYU_SELLERSPRITE_USERNAME', '').strip()
    secret = os.environ.get('CHENYU_SELLERSPRITE_PASSWORD', '')
    if args.action == 'status' and (reason := SessionStore(user).operation_block()):
        print(json.dumps({'login_status': 'blocked', 'block_reason': reason}))
        return 1
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        context, page, _ = launch_context(runtime, {'recover': args.action == 'recover'})
        try:
            result = ensure_login(page, user, secret, recover=args.action == 'recover',
                                  check_only=args.action == 'status')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            context.close()
    return 0 if result['login_status'] == 'verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())
