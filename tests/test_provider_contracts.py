# tests/test_provider_contracts.py

from voice_typing.providers.contracts import (
    ErrorCategory,
    EventKind,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
    TranscriptEvent,
    build_profile,
)


def test_event_kinds_have_expected_values():
    assert EventKind.PARTIAL.value == "partial"
    assert EventKind.FINAL.value == "final"
    assert EventKind.STATUS.value == "status"


def test_error_categories_cover_spec_taxonomy():
    values = {c.value for c in ErrorCategory}
    assert values == {"authentication", "network", "rate_limit", "unsupported", "invalid_configuration", "server"}


def test_transcript_event_factories():
    assert TranscriptEvent.partial("hel") == TranscriptEvent(EventKind.PARTIAL, "hel")
    assert TranscriptEvent.final("hello") == TranscriptEvent(EventKind.FINAL, "hello")
    assert TranscriptEvent.status("Ready").kind == EventKind.STATUS
    err = ProviderError(ErrorCategory.AUTHENTICATION, "bad key", False)
    failed = TranscriptEvent.failure(err)
    assert failed.error is err
    assert failed.kind == EventKind.STATUS


def test_provider_configuration_error_carries_category():
    exc = ProviderConfigurationError(ErrorCategory.UNSUPPORTED, "Unknown provider 'x'.")
    assert isinstance(exc, ValueError)
    assert exc.category == ErrorCategory.UNSUPPORTED
    assert exc.as_error() == ProviderError(ErrorCategory.UNSUPPORTED, "Unknown provider 'x'.", False)


def test_capabilities_default_to_all_false():
    caps = ProviderCapabilities()
    assert caps.streaming_stt is False
    assert caps.batch_stt is False
    assert caps.model_listing is False
    assert caps.text_cleanup is False


def test_build_profile_reads_saved_preset():
    data = {
        "provider_id": "openai_compatible",
        "provider_profiles": {
            "openai_compatible": {
                "base_url": "http://localhost:1234/v1",
                "api_key": "",
                "transcription_path": "/audio/transcriptions",
                "model": "whisper-large",
                "send_bearer_key": False,
                "skip_tls_verify": True,
            }
        },
    }
    profile = build_profile(data)
    assert profile.provider_id == "openai_compatible"
    assert profile.base_url == "http://localhost:1234/v1"
    assert profile.model == "whisper-large"
    assert profile.send_bearer_key is False
    assert profile.skip_tls_verify is True


def test_build_profile_defaults_to_gemini_live():
    profile = build_profile({})
    assert profile.provider_id == "gemini_live"
    assert profile.transcription_path == "/audio/transcriptions"
    assert profile.send_bearer_key is True
    assert profile.skip_tls_verify is False


def test_build_profile_missing_preset_yields_empty_profile():
    profile = build_profile({"provider_id": "groq", "provider_profiles": {}})
    assert profile.provider_id == "groq"
    assert profile.api_key == ""
    assert profile.model == ""
