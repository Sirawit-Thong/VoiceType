# tests/test_worker_cleanup.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from voice_typing.app import WorkerThread
from voice_typing.config.settings import SettingsManager
from voice_typing.providers.cleanup import GeminiCleanupProvider


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class FakeCleanup:
    def __init__(self, result=None, exc=None):
        self.calls = []
        self.result = result
        self.exc = exc

    async def cleanup(self, text, vocabulary=""):
        self.calls.append((text, vocabulary))
        if self.exc is not None:
            raise self.exc
        return self.result if self.result is not None else text


def _running_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def _wait_for_inject(mock_inject, count=1, timeout=2.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mock_inject.call_count >= count:
            return True
        time.sleep(0.02)
    return mock_inject.call_count >= count


def _worker(tmp_path, cleanup):
    mgr = SettingsManager(Path(tmp_path) / "s.json")
    mgr.load()
    worker = WorkerThread(mgr, cleanup_provider=cleanup)
    worker._recorder = MagicMock()
    worker._injector = MagicMock()
    return worker


def test_cleanup_success_injects_cleaned_once(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(result="Hello, world."))
    worker._loop = _running_loop()
    worker._inject_with_cleanup("hello world")
    worker._injector.inject.assert_called_once_with("Hello, world.")
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_cleanup_failure_injects_raw_once(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(exc=RuntimeError("down")))
    worker._loop = _running_loop()
    worker._inject_with_cleanup("raw text")
    worker._injector.inject.assert_called_once_with("raw text")
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_no_cleanup_provider_injects_directly(tmp_path):
    worker = _worker(tmp_path, None)
    worker._inject_with_cleanup("plain")
    worker._injector.inject.assert_called_once_with("plain")


def test_build_cleanup_provider_disabled_returns_none(tmp_path):
    worker = _worker(tmp_path, None)
    worker._profile = worker._snapshot_profile()
    assert worker._build_cleanup_provider() is None


def test_build_cleanup_provider_uses_same_gemini_profile(tmp_path):
    mgr = SettingsManager(Path(tmp_path) / "s.json")
    mgr.load()
    mgr.set("provider_id", "gemini_live")
    mgr.set("provider_profiles", {"gemini_live": {"api_key": "k", "model": "m"}})
    mgr.set("text_cleanup", {"enabled": True, "provider_id": ""})
    worker = WorkerThread(mgr)
    worker._profile = worker._snapshot_profile()
    provider = worker._build_cleanup_provider()
    assert isinstance(provider, GeminiCleanupProvider)


def test_finalize_uses_cleanup_when_enabled(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(result="Cleaned."))
    worker._loop = _running_loop()
    worker._recording = True
    worker._buffer.add_partial("raw")
    worker._finalize_and_inject()
    assert _wait_for_inject(worker._injector.inject, 1)
    worker._injector.inject.assert_called_once_with("Cleaned.")
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_connection_loss_flush_routes_through_cleanup(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(result="Cleaned after drop."))
    worker._loop = _running_loop()
    worker._recording = True
    worker._buffer.add_partial("raw after drop")
    worker._stop_recording_on_connection_lost()
    assert _wait_for_inject(worker._injector.inject, 1)
    worker._injector.inject.assert_called_once_with("Cleaned after drop.")
    assert worker._recording is False
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_connection_loss_duplicate_of_just_injected_final_is_suppressed(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(result="Same."))
    worker._loop = _running_loop()
    worker._recording = True
    worker._buffer.add_partial("same")
    worker._finalize_and_inject()
    assert _wait_for_inject(worker._injector.inject, 1)
    assert worker._injector.inject.call_count == 1
    worker._recording = True
    worker._buffer.add_partial("same")
    worker._stop_recording_on_connection_lost()
    # give async a chance to (incorrectly) inject again, then verify still 1
    import time as _t

    _t.sleep(0.3)
    assert worker._injector.inject.call_count == 1
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_connection_loss_cleanup_failure_injects_raw_once(tmp_path):
    worker = _worker(tmp_path, FakeCleanup(exc=RuntimeError("cleanup down")))
    worker._loop = _running_loop()
    worker._recording = True
    worker._buffer.add_partial("raw fallback")
    worker._stop_recording_on_connection_lost()
    assert _wait_for_inject(worker._injector.inject, 1)
    worker._injector.inject.assert_called_once_with("raw fallback")
    worker._loop.call_soon_threadsafe(worker._loop.stop)
