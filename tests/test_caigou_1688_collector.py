from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "chenyu-caigou"
    / "skills"
    / "chenyu-caigou"
    / "scripts"
    / "collector_1688.py"
)
SPEC = importlib.util.spec_from_file_location("chenyu_1688_collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(collector)


class RuntimeManager:
    def __init__(self, runtime):
        self.runtime = runtime

    def __enter__(self):
        return self.runtime

    def __exit__(self, *_args):
        return False


def test_url_allowlist_and_offer_normalization():
    assert collector.validate_1688_url("https://detail.1688.com/offer/123.html")
    try:
        collector.validate_1688_url("https://example.com/offer/123.html")
    except collector.Collector1688Error as exc:
        assert "does not allow host" in str(exc)
    else:
        raise AssertionError("external host must be rejected")

    rows = collector._normalize_search_records(
        [
            {
                "href": "https://detail.1688.com/offer/123.html?spm=test",
                "title": "木质出生公告牌",
                "price": "￥9.80",
            },
            {"href": "https://detail.1688.com/offer/123.html", "title": "重复"},
        ],
        "出生公告木牌",
        20,
    )
    assert len(rows) == 1
    assert rows[0]["offer_id"] == "123"
    assert rows[0]["product_url"] == "https://detail.1688.com/offer/123.html"
    assert rows[0]["source_keyword"] == "出生公告木牌"


def test_launch_uses_persistent_profile(tmp_path):
    runtime = mock.MagicMock()
    context = runtime.chromium.launch_persistent_context.return_value
    page = mock.MagicMock()
    context.pages = [page]
    profile = tmp_path / "profile"

    returned_context, returned_page, returned_profile = collector._launch_context(
        runtime,
        {"profile_dir": str(profile), "headless": False},
    )

    assert returned_context is context
    assert returned_page is page
    assert returned_profile == profile.resolve()
    kwargs = runtime.chromium.launch_persistent_context.call_args.kwargs
    assert kwargs["user_data_dir"] == str(profile.resolve())
    assert kwargs["headless"] is False


def test_headless_captcha_saves_checkpoint_and_resume_continues(tmp_path):
    run_dir = tmp_path / "run"
    profile = tmp_path / "profile"
    page = mock.MagicMock()
    page.url = "https://s.1688.com/verify"
    context = mock.MagicMock()
    runtime = mock.MagicMock()

    with (
        mock.patch.object(collector, "_require_playwright", return_value=lambda: RuntimeManager(runtime)),
        mock.patch.object(collector, "_launch_context", return_value=(context, page, profile)),
        mock.patch.object(collector, "_navigate_with_backoff"),
        mock.patch.object(collector, "detect_manual_gate", return_value="CAPTCHA_DETECTED"),
    ):
        blocked = collector.collect_1688_suppliers(
            {
                "query": "出生公告木牌",
                "run_dir": str(run_dir),
                "headless": True,
                "manual_timeout_seconds": 0,
                "detail_limit": 1,
            }
        )

    assert blocked["collection_status"] == "blocked"
    assert blocked["task_state"] == "CAPTCHA_DETECTED"
    checkpoint = json.loads((run_dir / "1688-checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["cursor"] == {"query_index": 0, "phase": "search", "detail_index": 0}
    assert checkpoint["config"]["profile_dir"] == str(profile)

    page.url = "https://s.1688.com/selloffer/offer_search.htm"
    record = {
        "source": "1688",
        "source_keyword": "出生公告木牌",
        "rank": 1,
        "offer_id": "123",
        "product_name": "木牌",
        "price": "￥9.80",
        "moq": "10件起批",
        "sales": None,
        "supplier": None,
        "location": None,
        "product_url": "https://detail.1688.com/offer/123.html",
        "image_url": None,
        "detail_collected": False,
        "observed_at": "2026-09-28T00:00:00+08:00",
    }
    with (
        mock.patch.object(collector, "_require_playwright", return_value=lambda: RuntimeManager(runtime)),
        mock.patch.object(collector, "_launch_context", return_value=(context, page, profile)),
        mock.patch.object(collector, "_navigate_with_backoff"),
        mock.patch.object(collector, "detect_manual_gate", return_value=None),
        mock.patch.object(collector, "_extract_search_records", return_value=[record]),
        mock.patch.object(
            collector,
            "_extract_detail",
            return_value={"supplier": "示例工厂", "detail_collected": True},
        ),
        mock.patch.object(collector, "_polite_delay"),
    ):
        completed = collector.collect_1688_suppliers(
            {"run_dir": str(run_dir), "headless": False},
            resume=True,
        )

    assert completed["collection_status"] == "complete"
    assert completed["task_state"] == "COMPLETE"
    assert completed["records"][0]["supplier"] == "示例工厂"
    assert completed["counts"]["details_collected"] == 1
    context.close.assert_called()


def test_manual_gate_detects_captcha_url_without_reading_page():
    page = mock.MagicMock()
    page.url = "https://s.1688.com/punish?x=1"
    assert collector.detect_manual_gate(page) == "CAPTCHA_DETECTED"
    assert collector._redacted_observed_url(page.url) == "https://s.1688.com/punish"


def test_visible_gate_wait_resumes_after_human_clearance():
    page = mock.MagicMock()
    page.is_closed.return_value = False
    with mock.patch.object(
        collector,
        "detect_manual_gate",
        side_effect=["CAPTCHA_DETECTED", "CAPTCHA_DETECTED", None],
    ):
        uncleared = collector._wait_for_manual_gate(page, timeout_seconds=5, poll_ms=500)

    assert uncleared is None
    assert page.wait_for_timeout.call_count == 2
