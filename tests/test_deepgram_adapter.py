# tests/test_deepgram_adapter.py
import asyncio
import json

import pytest

from voice_typing.providers.contracts import ErrorCategory, EventKind, ProviderProfile, TranscriptEvent
from voice_typing.providers.deepgram_adapter import DEEPGRAM_LISTEN_URL, DeepgramStreamingAdapter

FAKE_KEY = "dg_fake_test_key_0123456789abcdef"


class FakeWS:
    def __init__(self, incoming=None):
        self.sent = []
        self.sent_bytes = []
        self.incoming = list(incoming or [])
        self.closed = False

    async def send(self, message):
        if isinstance(message, (bytes, bytearray)):
            self.sent_bytes.append(bytes(message))
        else:
            self.sent.append(message)

    async def recv(self):
        if not self.incoming:
            raise asyncio.TimeoutError()
        return self.incoming.pop(0)

    async def close(self):
        self.closed = True


def _adapter(events, incoming=None):
    fake = FakeWS(incoming)

    async def factory(url, headers):
        factory.url = url
        factory.headers = headers
        return fake

    adapter = DeepgramStreamingAdapter(
        ProviderProfile(provider_id="deepgram", api_key=FAKE_KEY, model="nova-3"),
        events.append,
        connect_factory=factory,
    )
    return adapter, fake, factory


def _results(transcript, is_final):
    return json.dumps({
        "type": "Results",
        "channel": {"alternatives": [{"transcript": transcript}]},
        "is_final": is_final,
    })


def test_capabilities_are_streaming_only():
    caps = DeepgramStreamingAdapter.capabilities_of()
    assert caps.streaming_stt is True
    assert caps.batch_stt is False
    assert caps.model_listing is False
    assert caps.text_cleanup is False


def test_validate_rejects_missing_key():
    assert DeepgramStreamingAdapter.validate_profile(ProviderProfile(provider_id="deepgram", api_key="")).category == ErrorCategory.INVALID_CONFIGURATION
    assert DeepgramStreamingAdapter.validate_profile(ProviderProfile(provider_id="deepgram", api_key="k")) is None


@pytest.mark.asyncio
async def test_start_session_uses_token_header_and_query():
    events = []
    adapter, _fake, factory = _adapter(events)
    await adapter.start_session("thai", "")
    assert factory.url.startswith(DEEPGRAM_LISTEN_URL)
    assert "model=nova-3" in factory.url
    assert "encoding=linear16" in factory.url
    assert "sample_rate=16000" in factory.url
    assert "interim_results=true" in factory.url
    assert "language=th" in factory.url
    assert factory.headers == {"Authorization": f"Token {FAKE_KEY}"}
    assert FAKE_KEY not in factory.url
    await adapter.close()


@pytest.mark.asyncio
async def test_send_audio_forwards_raw_pcm():
    events = []
    adapter, fake, _factory = _adapter(events)
    await adapter.start_session("auto", "")
    await adapter.send_audio(b"\x00\x01\x02\x03")
    assert fake.sent_bytes == [b"\x00\x01\x02\x03"]
    await adapter.close()


@pytest.mark.asyncio
async def test_pump_emits_interim_then_final():
    events = []
    adapter, _fake, _factory = _adapter(events, [_results("hel", False), _results("hello", True)])
    await adapter.start_session("auto", "")
    await adapter.pump()
    await adapter.pump()
    assert events[0] == TranscriptEvent(EventKind.PARTIAL, "hel")
    assert events[1] == TranscriptEvent(EventKind.FINAL, "hello")
    await adapter.close()


@pytest.mark.asyncio
async def test_pump_ignores_empty_and_metadata():
    events = []
    adapter, _fake, _factory = _adapter(events, [_results("", False), json.dumps({"type": "Metadata"})])
    await adapter.start_session("auto", "")
    await adapter.pump()
    await adapter.pump()
    assert events == []
    await adapter.close()


@pytest.mark.asyncio
async def test_close_sends_close_stream():
    events = []
    adapter, fake, _factory = _adapter(events)
    await adapter.start_session("auto", "")
    await adapter.close()
    assert json.loads(fake.sent[0]) == {"type": "CloseStream"}
    assert fake.closed is True
    assert adapter.is_session_open is False
