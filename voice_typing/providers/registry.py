"""Adapter registry and factory. Adding a provider means one adapter class
plus tests plus a single register() line in build_default_registry()."""
from __future__ import annotations

from typing import Callable

from voice_typing.providers.contracts import (
    ErrorCategory,
    EventCallback,
    ProviderConfigurationError,
    ProviderError,
    ProviderProfile,
    SpeechProvider,
)


class ProviderRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, type[SpeechProvider]] = {}

    def register(self, provider_id: str, adapter: type[SpeechProvider]) -> None:
        if provider_id in self._adapters:
            raise KeyError(f"provider already registered: {provider_id}")
        self._adapters[provider_id] = adapter

    def get(self, provider_id: str) -> type[SpeechProvider]:
        try:
            return self._adapters[provider_id]
        except KeyError:
            raise ProviderConfigurationError(
                ErrorCategory.UNSUPPORTED, f"Unknown provider '{provider_id}'."
            ) from None

    def ids(self) -> list[str]:
        return sorted(self._adapters)


def build_default_registry() -> ProviderRegistry:
    from voice_typing.providers.deepgram_adapter import DeepgramStreamingAdapter
    from voice_typing.providers.gemini_adapter import GeminiStreamingAdapter
    from voice_typing.providers.openai_batch import GroqBatchAdapter, OpenAIBatchAdapter
    from voice_typing.providers.openai_realtime import OpenAIRealtimeAdapter

    registry = ProviderRegistry()
    registry.register("gemini_live", GeminiStreamingAdapter)
    registry.register("openai_realtime", OpenAIRealtimeAdapter)
    registry.register("groq", GroqBatchAdapter)
    registry.register("deepgram", DeepgramStreamingAdapter)
    registry.register("openai_compatible", OpenAIBatchAdapter)
    registry.register("freellm", OpenAIBatchAdapter)
    return registry


def create_provider(
    profile: ProviderProfile,
    on_event: EventCallback,
    registry: ProviderRegistry | None = None,
) -> SpeechProvider:
    reg = registry or build_default_registry()
    adapter_cls = reg.get(profile.provider_id)
    error = adapter_cls.validate_profile(profile)
    if error is not None:
        raise ProviderConfigurationError(error.category, error.message)
    return adapter_cls(profile, on_event)


def supports_dictation(
    profile: ProviderProfile, registry: ProviderRegistry | None = None
) -> ProviderError | None:
    reg = registry or build_default_registry()
    try:
        adapter_cls = reg.get(profile.provider_id)
    except ProviderConfigurationError as exc:
        return exc.as_error()
    return adapter_cls.validate_profile(profile)


Factory = Callable[[ProviderProfile, EventCallback], SpeechProvider]


def default_factory(profile: ProviderProfile, on_event: EventCallback) -> SpeechProvider:
    return create_provider(profile, on_event)
