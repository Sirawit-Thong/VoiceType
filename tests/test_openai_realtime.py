# tests/test_openai_realtime.py
import base64
import json

import pytest

from voice_typing.providers.contracts import (
    ErrorCategory,
    EventKind,
    ProviderProfile,
    TranscriptEvent,
)
from voice_typing.providers.openai_realtime import (
    OPENAI_REALTIME_URL,
    OpenAIRealtimeAdapter,
)

FAKE_KEY = "sk-fake-test-key-0123456789abcdefghij"


class FakeWS:
    def __init__(self, incoming=None):
        self.sent = []
        self.incoming = list(incoming or [])
        self.closed = False

    async def send(self, message):
        self.sent.append(message)

    async def recv(self):
        if not self.incoming:
            raise TimeoutError()
        return self.incoming.pop(0)

    async def close(self):
        self.closed = True


def _adapter(events, incoming=None, profile=None):
    fake = FakeWS(incoming)

    async def factory(url, headers):
        factory.url = url
        factory.headers = headers
        return fake

    adapter = OpenAIRealtimeAdapter(
        profile or ProviderProfile(provider_id="openai_realtime", api_key=FAKE_KEY, model="gpt-4o-mini-transcribe"),
        events.append,
        connect_factory=factory,
    )
    return adapter, fake, factory


def test_capabilities_cover_streaming_and_fallback():
    caps = OpenAIRealtimeAdapter.capabilities_of()
    assert caps.streaming_stt is True
    assert caps.batch_stt is True
    assert caps.text_cleanup is True


def test_validate_rejects_missing_key_and_bad_mode():
    assert OpenAIRealtimeAdapter.validate_profile(ProviderProfile(provider_id="openai_realtime", api_key="")).category == ErrorCategory.INVALID_CONFIGURATION
    bad = ProviderProfile(provider_id="openai_realtime", api_key="k", stt_mode="carrier-pigeon")
    assert OpenAIRealtimeAdapter.validate_profile(bad).category == ErrorCategory.INVALID_CONFIGURATION
    assert OpenAIRealtimeAdapter.validate_profile(ProviderProfile(provider_id="openai_realtime", api_key="k")) is None


@pytest.mark.asyncio
async def test_start_session_sends_config_without_key_leak():
    events = []
    adapter, fake, factory = _adapter(events)
    await adapter.start_session("english", "")
    assert factory.url.startswith(OPENAI_REALTIME_URL)
    assert "gpt-4o-mini-transcribe" in factory.url
    assert FAKE_KEY not in factory.url
    assert factory.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    assert factory.headers["OpenAI-Beta"] == "realtime=v1"
    config = json.loads(fake.sent[0])
    assert config["type"] == "transcription_session.update"
    assert config["session"]["input_audio_format"] == "pcm16"
    assert config["session"]["input_audio_transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert config["session"]["input_audio_transcription"]["language"] == "en"
    await adapter.close()
    assert fake.closed is True


@pytest.mark.asyncio
async def test_send_audio_forwards_base64_pcm():
    events = []
    adapter, fake, _factory = _adapter(events)
    await adapter.start_session("auto", "")
    await adapter.send_audio(b"\x00\x01")
    append = json.loads(fake.sent[1])
    assert append["type"] == "input_audio_buffer.append"
    assert base64.b64decode(append["audio"]) == b"\x00\x01"
    await adapter.close()


@pytest.mark.asyncio
async def test_pump_emits_partial_and_final():
    events = []
    incoming = [
        json.dumps({"type": "conversation.item.input_audio_transcription.delta", "delta": "hel"}),
        json.dumps({"type": "conversation.item.input_audio_transcription.completed", "transcript": "hello"}),
    ]
    adapter, _fake, _factory = _adapter(events, incoming)
    await adapter.start_session("auto", "")
    await adapter.pump()
    await adapter.pump()
    assert events[0] == TranscriptEvent(EventKind.PARTIAL, "hel")
    assert events[1] == TranscriptEvent(EventKind.FINAL, "hello")
    await adapter.close()


@pytest.mark.asyncio
async def test_pump_maps_error_without_key_leak():
    events = []
    incoming = [json.dumps({"type": "error", "error": {"code": "invalid_api_key", "message": f"bad {FAKE_KEY}"}})]
    adapter, _fake, _factory = _adapter(events, incoming)
    await adapter.start_session("auto", "")
    await adapter.pump()
    assert len(events) == 1
    assert events[0].error is not None
    assert FAKE_KEY not in events[0].error.message
    await adapter.close()


@pytest.mark.asyncio
async def test_batch_mode_delegates_upload():
    from voice_typing.providers.audio import pcm_to_wav_bytes

    async def fake_post(url, headers, form, timeout_sec, verify_tls):
        assert url == "https://api.openai.com/v1/audio/transcriptions"
        return 200, {"text": "hello upload"}

    events = []
    profile = ProviderProfile(provider_id="openai_realtime", api_key=FAKE_KEY, model="whisper-1", stt_mode="batch")
    adapter = OpenAIRealtimeAdapter(profile, events.append, http_post=fake_post)
    await adapter.start_session("auto", "")
    wav = pcm_to_wav_bytes(b"\x01\x02" * 800)
    event = await adapter.finish_turn(wav)
    assert event == TranscriptEvent(EventKind.FINAL, "hello upload")
    assert events == []
    await adapter.close()
