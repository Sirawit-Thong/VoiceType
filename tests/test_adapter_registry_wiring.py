# tests/test_adapter_registry_wiring.py
from voice_typing.providers.contracts import ErrorCategory, ProviderConfigurationError, ProviderProfile, build_profile
from voice_typing.providers.presets import PROVIDER_PRESETS
from voice_typing.providers.registry import build_default_registry, create_provider, supports_dictation


def test_all_presets_are_registered():
    registry = build_default_registry()
    assert sorted(registry.ids()) == ["deepgram", "freellm", "gemini_live", "groq", "openai_compatible", "openai_realtime"]


def test_registered_capabilities_match_presets():
    registry = build_default_registry()
    events = []
    for provider_id, preset in PROVIDER_PRESETS.items():
        profile = build_profile({"provider_id": provider_id, "provider_profiles": {provider_id: {}}}, provider_id)
        adapter_cls = registry.get(provider_id)
        probe = adapter_cls(profile, events.append)
        assert probe.capabilities == preset.capabilities


def test_empty_compatible_base_is_unavailable_for_dictation():
    registry = build_default_registry()
    profile = ProviderProfile(provider_id="openai_compatible", model="m")
    err = supports_dictation(profile, registry=registry)
    assert err is not None
    assert err.category == ErrorCategory.INVALID_CONFIGURATION
    assert "Base URL" in err.message


def test_chat_only_server_stays_unavailable_without_transcription_path_model():
    registry = build_default_registry()
    profile = ProviderProfile(provider_id="freellm", base_url="http://localhost:1234/v1", model="")
    err = supports_dictation(profile, registry=registry)
    assert err is not None
    assert err.category == ErrorCategory.INVALID_CONFIGURATION


def test_configured_batch_profile_creates_adapter():
    registry = build_default_registry()
    events = []
    provider = create_provider(
        ProviderProfile(provider_id="groq", api_key="gsk-fake-test-key-0123456789abcdef", model="whisper-large-v3-turbo"),
        events.append,
        registry=registry,
    )
    assert provider.capabilities.batch_stt is True


def test_unknown_provider_error_is_unsupported():
    registry = build_default_registry()
    try:
        create_provider(ProviderProfile(provider_id="ghost"), lambda e: None, registry=registry)
        raise AssertionError("expected ProviderConfigurationError")
    except ProviderConfigurationError as exc:
        assert exc.category == ErrorCategory.UNSUPPORTED
