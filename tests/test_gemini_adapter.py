# tests/test_gemini_adapter.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_typing.providers.contracts import (
    ErrorCategory,
    EventKind,
    ProviderProfile,
    TranscriptEvent,
)
from voice_typing.providers.gemini_adapter import (
    GEMINI_DEFAULT_MODEL,
    GeminiStreamingAdapter,
)

FAKE_KEY = "AIzaFakeTestKey0123456789abcdef"


def test_capabilities_match_preset():
    assert GeminiStreamingAdapter.capabilities_of().streaming_stt is True
    assert GeminiStreamingAdapter.capabilities_of().model_listing is True
    assert GeminiStreamingAdapter.capabilities_of().text_cleanup is True
    assert GeminiStreamingAdapter.capabilities_of().batch_stt is False


def test_validate_rejects_missing_key():
    err = GeminiStreamingAdapter.validate_profile(ProviderProfile(provider_id="gemini_live", api_key=""))
    assert err is not None
    assert err.category == ErrorCategory.INVALID_CONFIGURATION
    assert GeminiStreamingAdapter.validate_profile(ProviderProfile(provider_id="gemini_live", api_key="k")) is None


@pytest.mark.asyncio
async def test_start_session_uses_profile_model_and_language():
    ws = AsyncMock()
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        events = []
        adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY, model="my-model"), events.append)
        await adapter.start_session("thai", "")
        assert adapter.is_session_open is True
        setup = json.loads(ws.send.call_args_list[0].args[0])["setup"]
        assert setup["model"] == "models/my-model"
        assert "Thai" in setup["systemInstruction"]["parts"][0]["text"]
        await adapter.close()


@pytest.mark.asyncio
async def test_start_session_defaults_empty_model():
    ws = AsyncMock()
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY), lambda e: None)
        await adapter.start_session("auto", "")
        setup = json.loads(ws.send.call_args_list[0].args[0])["setup"]
        assert setup["model"] == GEMINI_DEFAULT_MODEL
        await adapter.close()


@pytest.mark.asyncio
async def test_pump_emits_partial_and_final_events():
    ws = AsyncMock()
    ws.recv = AsyncMock(side_effect=[
        json.dumps({"serverContent": {"inputTranscription": {"text": "hel"}, "turnComplete": False}}),
        json.dumps({"serverContent": {"inputTranscription": {"text": "hello"}, "turnComplete": True}}),
    ])
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        events = []
        adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY), events.append)
        await adapter.start_session("auto", "")
        await adapter.pump()
        await adapter.pump()
        await adapter.close()
    assert events[0] == TranscriptEvent(EventKind.PARTIAL, "hel")
    assert events[1] == TranscriptEvent(EventKind.FINAL, "hello")


@pytest.mark.asyncio
async def test_send_audio_forwards_pcm_after_start():
    ws = AsyncMock()
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY), lambda e: None)
        await adapter.send_audio(b"\x00\x01")
        assert ws.send.call_count == 0
        await adapter.start_session("auto", "")
        await adapter.send_audio(b"\x00\x01")
        assert ws.send.call_count == 2
        await adapter.close()


@pytest.mark.asyncio
async def test_finish_turn_returns_none_for_streaming():
    adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY), lambda e: None)
    assert await adapter.finish_turn(None) is None


@pytest.mark.asyncio
async def test_connect_failure_raises_redacted_network_error():
    async def boom(url):
        raise OSError(f"boom with key {FAKE_KEY}")
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=boom):
        adapter = GeminiStreamingAdapter(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY), lambda e: None)
        with pytest.raises(Exception) as exc_info:
            await adapter.start_session("auto", "")
    assert FAKE_KEY not in str(exc_info.value)


def test_list_models_redacts_key_on_auth_failure():
    import urllib.error

    error = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": "bad key"}'),
    )
    import asyncio

    async def run():
        with patch("urllib.request.urlopen", side_effect=error):
            await GeminiStreamingAdapter.list_models(ProviderProfile(provider_id="gemini_live", api_key=FAKE_KEY))

    with pytest.raises(Exception) as exc_info:
        asyncio.run(run())
    assert FAKE_KEY not in str(exc_info.value)
