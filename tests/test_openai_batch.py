# tests/test_openai_batch.py
import pytest

from voice_typing.providers.audio import pcm_to_wav_bytes
from voice_typing.providers.contracts import ErrorCategory, EventKind, ProviderProfile
from voice_typing.providers.openai_batch import (
    GroqBatchAdapter,
    OpenAIBatchAdapter,
    OpenAITranscriptionAdapter,
)


class FakeHTTP:
    def __init__(self, status=200, payload=None, exc=None):
        self.calls = []
        self.status = status
        self.payload = {"text": "hello world"} if payload is None else payload
        self.exc = exc

    async def __call__(self, url, headers, form, timeout_sec, verify_tls):
        self.calls.append({"url": url, "headers": dict(headers), "form": form, "timeout": timeout_sec, "verify": verify_tls})
        if self.exc is not None:
            raise self.exc
        return self.status, self.payload


def _wav():
    return pcm_to_wav_bytes(b"\x01\x02" * 800)


def test_transcription_url_joins_safely():
    profile = ProviderProfile(provider_id="groq", base_url="https://api.groq.com/openai/v1/", transcription_path="audio/transcriptions")
    assert GroqBatchAdapter.transcription_url(profile) == "https://api.groq.com/openai/v1/audio/transcriptions"


def test_build_request_carries_wav_model_and_bearer():
    http = FakeHTTP()
    adapter = OpenAITranscriptionAdapter(
        ProviderProfile(provider_id="openai_realtime", api_key="sk-fake-test-key-0123456789abcdefghij", model="whisper-1"),
        lambda e: None,
        http_post=http,
    )
    url, headers, fields = adapter.build_request(_wav())
    assert url == "https://api.openai.com/v1/audio/transcriptions"
    assert headers["Authorization"].startswith("Bearer sk-")
    assert fields["file"][1] == "audio.wav"
    assert fields["file"][2] == "audio/wav"
    assert fields["file"][0][:4] == b"RIFF"
    assert fields["model"] == "whisper-1"


def test_build_request_omits_auth_for_keyless_server():
    adapter = OpenAIBatchAdapter(
        ProviderProfile(provider_id="openai_compatible", base_url="http://localhost:1234/v1", model="m"),
        lambda e: None,
        http_post=FakeHTTP(),
    )
    _url, headers, _fields = adapter.build_request(_wav())
    assert "Authorization" not in headers


def test_build_request_uses_custom_key_header_when_bearer_disabled():
    adapter = OpenAIBatchAdapter(
        ProviderProfile(provider_id="openai_compatible", base_url="http://x/v1", model="m", api_key="k", send_bearer_key=False),
        lambda e: None,
        http_post=FakeHTTP(),
    )
    _url, headers, _fields = adapter.build_request(_wav())
    assert "Authorization" not in headers
    assert headers["x-api-key"] == "k"


@pytest.mark.asyncio
async def test_finish_turn_maps_response_text():
    http = FakeHTTP()
    adapter = GroqBatchAdapter(
        ProviderProfile(provider_id="groq", api_key="gsk-fake-test-key-0123456789abcdef", model="whisper-large-v3-turbo"),
        lambda e: None,
        http_post=http,
    )
    event = await adapter.finish_turn(_wav())
    assert event.kind == EventKind.FINAL
    assert event.text == "hello world"
    assert http.calls[0]["verify"] is True


@pytest.mark.asyncio
async def test_auth_failure_redacts_key():
    http = FakeHTTP(status=401, payload={"error": {"message": "bad key"}})
    adapter = GroqBatchAdapter(
        ProviderProfile(provider_id="groq", api_key="gsk-fake-test-key-0123456789abcdef"),
        lambda e: None,
        http_post=http,
    )
    with pytest.raises(Exception) as exc_info:
        await adapter.finish_turn(_wav())
    assert "gsk-fake-test-key-0123456789abcdef" not in str(exc_info.value)
    assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_status_mapping_covers_rate_limit_server_and_network():
    from voice_typing.providers.contracts import ProviderConfigurationError

    rate = GroqBatchAdapter(ProviderProfile(provider_id="groq", api_key="k"), lambda e: None, http_post=FakeHTTP(status=429, payload={}))
    with pytest.raises(ProviderConfigurationError) as info:
        await rate.finish_turn(_wav())
    assert info.value.category == ErrorCategory.RATE_LIMIT

    server = GroqBatchAdapter(ProviderProfile(provider_id="groq", api_key="k"), lambda e: None, http_post=FakeHTTP(status=500, payload={}))
    with pytest.raises(ProviderConfigurationError) as info2:
        await server.finish_turn(_wav())
    assert info2.value.category == ErrorCategory.SERVER
    assert info2.value.as_error().retryable is True

    broken = GroqBatchAdapter(ProviderProfile(provider_id="groq", api_key="k"), lambda e: None, http_post=FakeHTTP(exc=OSError("down")))
    with pytest.raises(ProviderConfigurationError) as info3:
        await broken.finish_turn(_wav())
    assert info3.value.category == ErrorCategory.NETWORK


@pytest.mark.asyncio
async def test_finish_turn_without_audio_returns_empty_final():
    adapter = GroqBatchAdapter(ProviderProfile(provider_id="groq", api_key="k"), lambda e: None, http_post=FakeHTTP())
    event = await adapter.finish_turn(None)
    assert event.kind == EventKind.FINAL
    assert event.text == ""


def test_groq_defaults_and_key_requirement():
    assert GroqBatchAdapter.effective_base_url(ProviderProfile(provider_id="groq")) == "https://api.groq.com/openai/v1"
    assert GroqBatchAdapter.effective_model(ProviderProfile(provider_id="groq")) == "whisper-large-v3-turbo"
    err = GroqBatchAdapter.validate_profile(ProviderProfile(provider_id="groq", api_key=""))
    assert err is not None and err.category == ErrorCategory.INVALID_CONFIGURATION


def test_compatible_requires_base_and_model():
    assert OpenAIBatchAdapter.validate_profile(ProviderProfile(provider_id="openai_compatible", model="m")).category == ErrorCategory.INVALID_CONFIGURATION
    assert OpenAIBatchAdapter.validate_profile(ProviderProfile(provider_id="openai_compatible", base_url="http://x/v1")).category == ErrorCategory.INVALID_CONFIGURATION
    assert OpenAIBatchAdapter.validate_profile(ProviderProfile(provider_id="openai_compatible", base_url="http://x/v1", model="m")) is None
