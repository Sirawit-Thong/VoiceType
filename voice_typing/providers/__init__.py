"""Pluggable speech-to-text providers. UI and WorkerThread depend only on contracts."""
from voice_typing.providers.contracts import (
    ErrorCategory,
    EventCallback,
    EventKind,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
    ProviderProfile,
    SpeechProvider,
    TextCleanupProvider,
    TranscriptEvent,
    build_profile,
)

__all__ = [
    "ErrorCategory",
    "EventCallback",
    "EventKind",
    "ProviderCapabilities",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderProfile",
    "SpeechProvider",
    "TextCleanupProvider",
    "TranscriptEvent",
    "build_profile",
]
