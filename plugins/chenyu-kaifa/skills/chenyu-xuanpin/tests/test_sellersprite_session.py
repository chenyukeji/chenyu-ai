import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import playwright_collector as collector


class SessionTests(unittest.TestCase):
    def test_password_login_alternative_is_not_a_security_challenge(self):
        page = MagicMock()
        page.locator.return_value.first.is_visible.return_value = False
        page.locator.return_value.inner_text.return_value = "账号密码登录\n验证码登录 找回密码"
        self.assertFalse(collector._challenge_visible(page))

    def test_real_challenge_controls_and_instructions_still_block(self):
        page = MagicMock()
        page.locator.return_value.first.is_visible.return_value = True
        self.assertTrue(collector._challenge_visible(page))
        page.locator.return_value.first.is_visible.return_value = False
        for text in ("请输入验证码", "请完成安全验证", "向右滑动完成验证", "人机验证", "Robot Check"):
            with self.subTest(text=text):
                page.locator.return_value.inner_text.return_value = text
                self.assertTrue(collector._challenge_visible(page))

    def test_password_login_runs_with_verification_login_link_present(self):
        page = MagicMock()
        page.url = "https://www.sellersprite.com/cn/w/user/login"
        page.locator.return_value.first.is_visible.return_value = False
        page.locator.return_value.inner_text.return_value = "验证码登录 找回密码"
        with patch.object(collector, "_require_playwright", return_value=MagicMock()), \
             patch.object(collector, "_launch_context", return_value=(MagicMock(), page, Path("/tmp/profile"))), \
             patch.object(collector, "_sellersprite_credentials", return_value=("test", "secret", "environment")), \
             patch.object(collector, "_goto"), \
             patch.object(collector, "_wait_for_sellersprite_session", return_value="sellersprite_login_unverified"), \
             patch.object(collector, "_login_sellersprite_in_page", return_value={"login_status": "failed", "block_reason": "invalid_credentials"}) as login:
            result = collector.collect_sellersprite_by_asin({"marketplace": "US", "asins": ["B012345678"]})
        login.assert_called_once()
        self.assertTrue(result["source_metadata"]["login_attempted"])
        self.assertEqual(result["block_reason"], "invalid_credentials")

    def test_session_cookie_survives_new_browser_context(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CHENYU_SELLERSPRITE_USERNAME": "test-account"}):
            path = Path(folder) / "sellersprite-session.json"
            cookie = {"name": "session", "value": "test-session", "domain": ".sellersprite.com", "path": "/", "expires": -1}
            old_context = MagicMock()
            old_context._chenyu_sellersprite_session_path = path
            old_context.cookies.return_value = [cookie, {**cookie, "domain": "amazon.com"}]
            collector._save_sellersprite_session(old_context)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            new_context = MagicMock()
            collector._restore_sellersprite_session(new_context, path)
            new_context.add_cookies.assert_called_once_with([cookie])

    def test_expired_or_foreign_cookies_are_not_restored(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CHENYU_SELLERSPRITE_USERNAME": "test-account"}):
            path = Path(folder) / "sellersprite-session.json"
            path.write_text(json.dumps({"account": "test-account", "cookies": [{"domain": "sellersprite.com", "expires": 1}, {"domain": "fake-sellersprite.com", "expires": -1}]}))
            context = MagicMock()
            collector._restore_sellersprite_session(context, path)
            context.add_cookies.assert_not_called()

    def test_changed_account_and_corrupt_state_do_not_restore(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CHENYU_SELLERSPRITE_USERNAME": "new-account"}):
            path = Path(folder) / "sellersprite-session.json"
            context = MagicMock()
            path.write_text(json.dumps({"account": "old-account", "cookies": [{"domain": "sellersprite.com", "expires": -1}]}))
            collector._restore_sellersprite_session(context, path)
            path.write_text("invalid")
            collector._restore_sellersprite_session(context, path)
            context.add_cookies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
