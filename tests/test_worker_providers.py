# tests/test_worker_providers.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from unittest.mock import MagicMock

from voice_typing.app import WorkerThread
from voice_typing.config.settings import SettingsManager
from voice_typing.providers.contracts import ProviderCapabilities, ProviderProfile, TranscriptEvent


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class FakeStreamingProvider:
    capabilities = ProviderCapabilities(streaming_stt=True)
    started_with = None
    sent_audio = None
    closed = False

    def __init__(self, profile, on_event):
        self._profile = profile
        self._on_event = on_event
        FakeStreamingProvider.sent_audio = []
        FakeStreamingProvider.closed = False

    async def start_session(self, language, vocabulary):
        FakeStreamingProvider.started_with = (language, vocabulary)

    async def send_audio(self, pcm):
        FakeStreamingProvider.sent_audio.append(pcm)

    async def pump(self):
        return None

    async def finish_turn(self, wav_bytes=None):
        return None

    async def close(self):
        FakeStreamingProvider.closed = True


def _worker(tmp_path, factory):
    mgr = SettingsManager(Path(tmp_path) / "s.json")
    mgr.load()
    mgr.set("api_key", "k")
    mgr.set("provider_id", "gemini_live")
    mgr.set("provider_profiles", {"gemini_live": {"api_key": "k", "model": "m"}})
    worker = WorkerThread(mgr, provider_factory=factory)
    worker._recorder = MagicMock()
    worker._injector = MagicMock()
    return worker


def test_snapshot_uses_active_provider_profile(tmp_path):
    worker = _worker(tmp_path, lambda profile, on_event: FakeStreamingProvider(profile, on_event))
    snapshot = worker._snapshot_profile()
    assert isinstance(snapshot, ProviderProfile)
    assert snapshot.provider_id == "gemini_live"
    assert snapshot.api_key == "k"
    assert snapshot.model == "m"


def test_streaming_partial_updates_buffer_and_signal(tmp_path):
    worker = _worker(tmp_path, lambda profile, on_event: FakeStreamingProvider(profile, on_event))
    worker._provider = FakeStreamingProvider(worker._snapshot_profile(), worker._on_provider_event)
    worker._supports_streaming = True
    partials = []
    worker._signals.partial_received.connect(partials.append)
    worker._on_provider_event(TranscriptEvent.partial("hel"))
    assert worker._buffer.current == "hel"
    assert partials == ["hel"]


def test_streaming_final_injects_once(tmp_path):
    worker = _worker(tmp_path, lambda profile, on_event: FakeStreamingProvider(profile, on_event))
    worker._provider = FakeStreamingProvider(worker._snapshot_profile(), worker._on_provider_event)
    worker._supports_streaming = True
    worker._recording = True
    worker._on_provider_event(TranscriptEvent.partial("hello"))
    worker._on_provider_event(TranscriptEvent.final("hello"))
    worker._injector.inject.assert_called_once_with("hello")


def test_status_event_maps_to_generic_status_signal(tmp_path):
    worker = _worker(tmp_path, lambda profile, on_event: FakeStreamingProvider(profile, on_event))
    worker._provider = FakeStreamingProvider(worker._snapshot_profile(), worker._on_provider_event)
    worker._supports_streaming = True
    seen = []
    worker._signals.status.connect(seen.append)
    worker._on_provider_event(TranscriptEvent.status("Connecting..."))
    assert seen == ["Connecting..."]
