# tests/test_provider_registry.py
import pytest

from voice_typing.providers.contracts import (
    ErrorCategory,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderProfile,
)
from voice_typing.providers.presets import PROVIDER_ORDER, PROVIDER_PRESETS
from voice_typing.providers.registry import (
    ProviderRegistry,
    build_default_registry,
    create_provider,
    supports_dictation,
)


def test_presets_cover_all_six_provider_ids():
    assert set(PROVIDER_PRESETS) == {"gemini_live", "openai_realtime", "groq", "deepgram", "openai_compatible", "freellm"}
    assert list(PROVIDER_ORDER) == ["gemini_live", "openai_realtime", "groq", "deepgram", "openai_compatible", "freellm"]


def test_preset_capabilities_match_spec_modes():
    assert PROVIDER_PRESETS["gemini_live"].capabilities.streaming_stt is True
    assert PROVIDER_PRESETS["gemini_live"].capabilities.model_listing is True
    assert PROVIDER_PRESETS["groq"].capabilities.batch_stt is True
    assert PROVIDER_PRESETS["groq"].capabilities.streaming_stt is False
    assert PROVIDER_PRESETS["deepgram"].capabilities.streaming_stt is True
    assert PROVIDER_PRESETS["deepgram"].capabilities.batch_stt is False
    assert PROVIDER_PRESETS["openai_compatible"].capabilities.batch_stt is True
    assert PROVIDER_PRESETS["freellm"].needs_api_key is False
    assert PROVIDER_PRESETS["openai_compatible"].needs_api_key is False
    assert PROVIDER_PRESETS["gemini_live"].needs_api_key is True


def test_groq_preset_pins_safe_defaults():
    preset = PROVIDER_PRESETS["groq"]
    assert preset.default_base_url == "https://api.groq.com/openai/v1"
    assert preset.default_model == "whisper-large-v3-turbo"


def test_registry_rejects_unknown_provider():
    registry = build_default_registry()
    events = []
    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_provider(ProviderProfile(provider_id="nope"), events.append, registry=registry)
    assert exc_info.value.category == ErrorCategory.UNSUPPORTED
    assert "nope" in str(exc_info.value)


def test_registry_rejects_duplicate_registration():
    from voice_typing.providers.gemini_adapter import GeminiStreamingAdapter
    registry = ProviderRegistry()
    registry.register("gemini_live", GeminiStreamingAdapter)
    with pytest.raises(KeyError):
        registry.register("gemini_live", GeminiStreamingAdapter)


def test_default_registry_creates_gemini_adapter():
    registry = build_default_registry()
    assert "gemini_live" in registry.ids()
    events = []
    provider = create_provider(ProviderProfile(provider_id="gemini_live", api_key="k", model="m"), events.append, registry=registry)
    assert provider.capabilities == ProviderCapabilities(streaming_stt=True, model_listing=True, text_cleanup=True)


def test_create_provider_rejects_invalid_profile():
    registry = build_default_registry()
    events = []
    with pytest.raises(ProviderConfigurationError) as exc_info:
        create_provider(ProviderProfile(provider_id="gemini_live", api_key=""), events.append, registry=registry)
    assert exc_info.value.category == ErrorCategory.INVALID_CONFIGURATION


def test_supports_dictation_reports_unconfigured_gemini():
    registry = build_default_registry()
    err = supports_dictation(ProviderProfile(provider_id="gemini_live", api_key=""), registry=registry)
    assert err is not None
    assert err.category == ErrorCategory.INVALID_CONFIGURATION
    ok = supports_dictation(ProviderProfile(provider_id="gemini_live", api_key="k"), registry=registry)
    assert ok is None
