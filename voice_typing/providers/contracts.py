"""Provider-neutral contracts for speech-to-text and text cleanup.

UI and WorkerThread depend only on these types. Network protocols and
provider-specific payload parsing live in the adapter modules.

Delivery rule: streaming adapters emit TranscriptEvent via the on_event
callback during pump() and return None from finish_turn(). Batch adapters
ignore send_audio(), do nothing in pump(), and return the final
TranscriptEvent from finish_turn(wav_bytes) without emitting via callback.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ErrorCategory(str, Enum):
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    UNSUPPORTED = "unsupported"
    INVALID_CONFIGURATION = "invalid_configuration"
    SERVER = "server"


RETRYABLE_CATEGORIES = frozenset({ErrorCategory.NETWORK, ErrorCategory.SERVER, ErrorCategory.RATE_LIMIT})


class EventKind(str, Enum):
    PARTIAL = "partial"
    FINAL = "final"
    STATUS = "status"


@dataclass(frozen=True)
class ProviderError:
    category: ErrorCategory
    message: str
    retryable: bool = False


class ProviderConfigurationError(ValueError):
    def __init__(self, category: ErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message

    def as_error(self) -> ProviderError:
        return ProviderError(self.category, self.message, self.category in RETRYABLE_CATEGORIES)


@dataclass(frozen=True)
class TranscriptEvent:
    kind: EventKind
    text: str = ""
    error: ProviderError | None = None

    @staticmethod
    def partial(text: str) -> TranscriptEvent:
        return TranscriptEvent(EventKind.PARTIAL, text)

    @staticmethod
    def final(text: str) -> TranscriptEvent:
        return TranscriptEvent(EventKind.FINAL, text)

    @staticmethod
    def status(text: str) -> TranscriptEvent:
        return TranscriptEvent(EventKind.STATUS, text)

    @staticmethod
    def failure(error: ProviderError) -> TranscriptEvent:
        return TranscriptEvent(EventKind.STATUS, "", error)


@dataclass(frozen=True)
class ProviderCapabilities:
    streaming_stt: bool = False
    batch_stt: bool = False
    model_listing: bool = False
    text_cleanup: bool = False


@dataclass(frozen=True)
class ProviderProfile:
    provider_id: str
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    transcription_path: str = "/audio/transcriptions"
    send_bearer_key: bool = True
    skip_tls_verify: bool = False
    stt_mode: str = "default"
    options: dict[str, str] = field(default_factory=dict)


EventCallback = Callable[[TranscriptEvent], None]


class SpeechProvider(ABC):
    def __init__(self, profile: ProviderProfile, on_event: EventCallback) -> None:
        self._profile = profile
        self._on_event = on_event

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @classmethod
    @abstractmethod
    def validate_profile(cls, profile: ProviderProfile) -> ProviderError | None: ...

    @classmethod
    @abstractmethod
    async def list_models(cls, profile: ProviderProfile) -> list[str]: ...

    @abstractmethod
    async def start_session(self, language: str, vocabulary: str) -> None: ...

    @abstractmethod
    async def send_audio(self, pcm: bytes) -> None: ...

    @abstractmethod
    async def pump(self) -> None: ...

    @abstractmethod
    async def finish_turn(self, wav_bytes: bytes | None = None) -> TranscriptEvent | None: ...

    @abstractmethod
    async def close(self) -> None: ...


class TextCleanupProvider(ABC):
    @abstractmethod
    async def cleanup(self, text: str, vocabulary: str = "") -> str: ...


def build_profile(settings_data: dict[str, Any], provider_id: str = "") -> ProviderProfile:
    pid = provider_id or str(settings_data.get("provider_id", "gemini_live") or "gemini_live")
    profiles = settings_data.get("provider_profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    raw = profiles.get(pid)
    if not isinstance(raw, dict):
        raw = {}
    options = raw.get("options")
    return ProviderProfile(
        provider_id=pid,
        api_key=str(raw.get("api_key", "") or ""),
        model=str(raw.get("model", "") or ""),
        base_url=str(raw.get("base_url", "") or ""),
        transcription_path=str(raw.get("transcription_path", "/audio/transcriptions") or "/audio/transcriptions"),
        send_bearer_key=bool(raw.get("send_bearer_key", True)),
        skip_tls_verify=bool(raw.get("skip_tls_verify", False)),
        stt_mode=str(raw.get("stt_mode", "default") or "default"),
        options={str(k): str(v) for k, v in options.items()} if isinstance(options, dict) else {},
    )
