# voice_typing/providers/openai_batch.py
"""Batch transcription against OpenAI-style /audio/transcriptions endpoints.

One class serves OpenAI, Groq, generic compatible servers, and the FreeLLM
preset; subclasses only pin safe defaults. Network is injected via http_post
so contract tests run against fakes.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from voice_typing.providers.contracts import (
    ErrorCategory,
    ProviderCapabilities,
    ProviderConfigurationError,
    ProviderError,
    ProviderProfile,
    SpeechProvider,
    TranscriptEvent,
)
from voice_typing.providers.redaction import redact_text, safe_error

HttpPost = Callable[[str, dict[str, str], aiohttp.FormData, float, bool], Awaitable[tuple[int, dict[str, Any]]]]

_BATCH_CAPS = ProviderCapabilities(batch_stt=True, text_cleanup=True)


async def _default_post(
    url: str, headers: dict[str, str], form: aiohttp.FormData, timeout_sec: float, verify_tls: bool
) -> tuple[int, dict[str, Any]]:
    connector = None if verify_tls else aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session, session.post(
        url, headers=headers, data=form
    ) as resp:
        try:
            payload = await resp.json()
        except Exception:
            payload = {}
        return resp.status, payload if isinstance(payload, dict) else {}


class OpenAIBatchAdapter(SpeechProvider):
    DEFAULT_BASE_URL = ""
    DEFAULT_MODEL = ""
    DEFAULT_TRANSCRIPTION_PATH = "/audio/transcriptions"
    REQUIRES_API_KEY = False

    def __init__(self, profile: ProviderProfile, on_event, http_post: HttpPost | None = None) -> None:
        super().__init__(profile, on_event)
        self._http_post = http_post or _default_post
        self._language = "auto"

    @classmethod
    def capabilities_of(cls) -> ProviderCapabilities:
        return _BATCH_CAPS

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _BATCH_CAPS

    @classmethod
    def effective_base_url(cls, profile: ProviderProfile) -> str:
        return profile.base_url.strip() or cls.DEFAULT_BASE_URL

    @classmethod
    def effective_model(cls, profile: ProviderProfile) -> str:
        return profile.model.strip() or cls.DEFAULT_MODEL

    @classmethod
    def transcription_url(cls, profile: ProviderProfile) -> str:
        base = cls.effective_base_url(profile).rstrip("/")
        path = (profile.transcription_path.strip() or cls.DEFAULT_TRANSCRIPTION_PATH).strip()
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    @classmethod
    def validate_profile(cls, profile: ProviderProfile) -> ProviderError | None:
        if cls.REQUIRES_API_KEY and not profile.api_key.strip():
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "API key is required.")
        if not cls.effective_base_url(profile):
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "Base URL is required.")
        if not cls.effective_model(profile):
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "Model is required.")
        return None

    @classmethod
    async def list_models(cls, profile: ProviderProfile) -> list[str]:
        return []

    def build_request(self, wav_bytes: bytes) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = self.transcription_url(self._profile)
        headers: dict[str, str] = {}
        key = self._profile.api_key.strip()
        if key and self._profile.send_bearer_key:
            headers["Authorization"] = f"Bearer {key}"
        elif key:
            headers["x-api-key"] = key
        fields: dict[str, Any] = {
            "file": (wav_bytes, "audio.wav", "audio/wav"),
            "model": self.effective_model(self._profile),
        }
        if self._language not in ("", "auto"):
            fields["language"] = self._language
        return url, headers, fields

    async def start_session(self, language: str, vocabulary: str) -> None:
        error = self.validate_profile(self._profile)
        if error is not None:
            raise ProviderConfigurationError(error.category, error.message)
        self._language = language

    async def send_audio(self, pcm: bytes) -> None:
        return None

    async def pump(self) -> None:
        return None

    async def finish_turn(self, wav_bytes: bytes | None = None) -> TranscriptEvent | None:
        if not wav_bytes:
            return TranscriptEvent.final("")
        error = self.validate_profile(self._profile)
        if error is not None:
            raise ProviderConfigurationError(error.category, error.message)
        text = await self.transcribe_wav(wav_bytes)
        return TranscriptEvent.final(text)

    async def transcribe_wav(self, wav_bytes: bytes, timeout_sec: float = 60.0) -> str:
        url, headers, fields = self.build_request(wav_bytes)
        form = aiohttp.FormData()
        file_bytes, filename, content_type = fields["file"]
        form.add_field("file", file_bytes, filename=filename, content_type=content_type)
        form.add_field("model", fields["model"])
        if "language" in fields:
            form.add_field("language", fields["language"])
        try:
            status, payload = await self._http_post(url, headers, form, timeout_sec, not self._profile.skip_tls_verify)
        except Exception as exc:
            raise ProviderConfigurationError(ErrorCategory.NETWORK, safe_error(exc, "Upload failed: ")) from exc
        if status == 200:
            text = payload.get("text", "")
            return text if isinstance(text, str) else ""
        detail = redact_text(str(payload.get("error", payload))[:200])
        if status in (401, 403):
            raise ProviderConfigurationError(ErrorCategory.AUTHENTICATION, f"Transcription rejected ({status}): {detail}")
        if status == 429:
            raise ProviderConfigurationError(ErrorCategory.RATE_LIMIT, f"Transcription rate limited (429): {detail}")
        if status >= 500:
            raise ProviderConfigurationError(ErrorCategory.SERVER, f"Transcription server error ({status}): {detail}")
        raise ProviderConfigurationError(ErrorCategory.SERVER, f"Transcription failed ({status}): {detail}")

    async def close(self) -> None:
        return None


class OpenAITranscriptionAdapter(OpenAIBatchAdapter):
    DEFAULT_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "whisper-1"
    REQUIRES_API_KEY = True


class GroqBatchAdapter(OpenAIBatchAdapter):
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "whisper-large-v3-turbo"
    REQUIRES_API_KEY = True
    KNOWN_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3", "distil-whisper-large-v3-en")
