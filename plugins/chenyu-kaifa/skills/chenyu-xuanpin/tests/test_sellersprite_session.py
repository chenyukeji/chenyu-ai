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
