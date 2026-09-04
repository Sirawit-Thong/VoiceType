# tests/test_worker_batch.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import array
import asyncio
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from voice_typing.app import WorkerThread
from voice_typing.config.settings import SettingsManager
from voice_typing.providers.contracts import (
    ProviderCapabilities,
    TranscriptEvent,
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class FakeBatchProvider:
    capabilities = ProviderCapabilities(batch_stt=True)
    last_wav = None
    calls = 0

    def __init__(self, profile, on_event):
        self._profile = profile
        self._on_event = on_event

    async def start_session(self, language, vocabulary):
        return None

    async def send_audio(self, pcm):
        return None

    async def pump(self):
        return None

    async def finish_turn(self, wav_bytes=None):
        FakeBatchProvider.calls += 1
        FakeBatchProvider.last_wav = wav_bytes
        assert wav_bytes is not None and wav_bytes[:4] == b"RIFF"
        return TranscriptEvent.final("hello batch")

    async def close(self):
        return None


def _running_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop


def _batch_worker(tmp_path):
    mgr = SettingsManager(Path(tmp_path) / "s.json")
    mgr.load()
    mgr.set("provider_id", "groq")
    mgr.set("provider_profiles", {"groq": {"api_key": "k", "model": "whisper-large-v3-turbo"}})
    worker = WorkerThread(mgr, provider_factory=lambda profile, on_event: FakeBatchProvider(profile, on_event))
    worker._recorder = MagicMock()
    worker._injector = MagicMock()
    worker._provider = FakeBatchProvider(worker._snapshot_profile(), worker._on_provider_event)
    worker._client = worker._provider
    worker._supports_streaming = False
    worker._loop = _running_loop()
    worker._recording = True
    return worker


def test_batch_release_uploads_wav_and_injects_once(tmp_path):
    FakeBatchProvider.calls = 0
    worker = _batch_worker(tmp_path)
    worker._pcm_buffer.extend(array.array("h", [1000] * 1600).tobytes())
    statuses = []
    worker._signals.status.connect(statuses.append)
    worker._finish_batch_turn()
    assert FakeBatchProvider.calls == 1
    assert FakeBatchProvider.last_wav[:4] == b"RIFF"
    worker._injector.inject.assert_called_once_with("hello batch")
    assert "Transcribing..." in statuses
    assert statuses[-1] == "Ready"
    assert worker._recording is False
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_batch_ignores_partial_events(tmp_path):
    worker = _batch_worker(tmp_path)
    partials = []
    worker._signals.partial_received.connect(partials.append)
    worker._on_provider_event(TranscriptEvent.partial("hel"))
    assert partials == []
    assert worker._buffer.current == ""
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_batch_empty_buffer_uploads_nothing(tmp_path):
    FakeBatchProvider.calls = 0
    worker = _batch_worker(tmp_path)
    assert len(worker._pcm_buffer) == 0
    worker._finish_batch_turn()
    assert FakeBatchProvider.calls == 0
    worker._injector.inject.assert_not_called()
    assert worker._recording is False
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_batch_release_reroutes_hotkey_release(tmp_path):
    worker = _batch_worker(tmp_path)
    worker._pcm_buffer.extend(array.array("h", [1000] * 160).tobytes())
    worker._on_hotkey_release(0x78)
    worker._injector.inject.assert_called_once_with("hello batch")
    worker._loop.call_soon_threadsafe(worker._loop.stop)


class _FakeCleanupForBatch:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def cleanup(self, text, vocabulary=""):
        self.calls.append((text, vocabulary))
        return self.result


def _batch_worker_with_cleanup(tmp_path, cleanup):
    worker = _batch_worker(tmp_path)
    worker._cleanup_provider = cleanup
    return worker


def test_batch_final_with_cleanup_injects_cleaned_once(tmp_path):
    cleanup = _FakeCleanupForBatch("Hello, batch.")
    worker = _batch_worker_with_cleanup(tmp_path, cleanup)
    worker._on_final("hello batch")
    assert _wait_for_batch_inject(worker._injector.inject, 1)
    worker._injector.inject.assert_called_once_with("Hello, batch.")
    assert cleanup.calls == [("hello batch", "")]
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def _wait_for_batch_inject(mock_inject, count=1, timeout=2.0):
    import time as _t

    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        if mock_inject.call_count >= count:
            return True
        _t.sleep(0.02)
    return mock_inject.call_count >= count


def test_batch_duplicate_within_half_second_injects_once(tmp_path):
    cleanup = _FakeCleanupForBatch("Hello, batch.")
    worker = _batch_worker_with_cleanup(tmp_path, cleanup)
    worker._on_final("hello batch")
    worker._on_final("hello batch")
    assert _wait_for_batch_inject(worker._injector.inject, 1)
    worker._injector.inject.assert_called_once_with("Hello, batch.")
    worker._loop.call_soon_threadsafe(worker._loop.stop)


def test_batch_final_without_cleanup_routes_through_processor(tmp_path):
    worker = _batch_worker(tmp_path)
    worker._cleanup_provider = None
    fake_processor = MagicMock()
    fake_future = MagicMock()
    fake_future.result.return_value = "PROCESSED batch"
    # Non-blocking path uses add_done_callback — invoke immediately.
    fake_future.add_done_callback.side_effect = lambda cb: cb(fake_future)
    with patch("asyncio.run_coroutine_threadsafe", return_value=fake_future):
        worker._processor = fake_processor
        worker._on_final("hello batch")
    worker._injector.inject.assert_called_once_with("PROCESSED batch")
    worker._loop.call_soon_threadsafe(worker._loop.stop)
