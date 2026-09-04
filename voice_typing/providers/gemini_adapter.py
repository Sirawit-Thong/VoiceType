"""Gemini Live streaming adapter. Wraps voice_typing.speech.gemini_live
without forking its wire protocol."""
from __future__ import annotations

import asyncio

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
from voice_typing.speech.gemini_live import MODEL, GeminiLiveClient, fetch_live_models

GEMINI_DEFAULT_MODEL = MODEL

_GEMINI_CAPS = ProviderCapabilities(streaming_stt=True, model_listing=True, text_cleanup=True)


class GeminiStreamingAdapter(SpeechProvider):
    def __init__(self, profile: ProviderProfile, on_event) -> None:
        super().__init__(profile, on_event)
        self._client: GeminiLiveClient | None = None

    @classmethod
    def capabilities_of(cls) -> ProviderCapabilities:
        return _GEMINI_CAPS

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _GEMINI_CAPS

    @property
    def is_session_open(self) -> bool:
        return self._client is not None and self._client.is_connected

    @classmethod
    def validate_profile(cls, profile: ProviderProfile) -> ProviderError | None:
        if not profile.api_key.strip():
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "Gemini API key is required.")
        return None

    @classmethod
    async def list_models(cls, profile: ProviderProfile) -> list[str]:
        try:
            return await asyncio.to_thread(fetch_live_models, profile.api_key)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            text = str(exc)
            if "401" in text or "403" in text or "API key" in text:
                category = ErrorCategory.AUTHENTICATION
            else:
                category = ErrorCategory.NETWORK
            raise ProviderConfigurationError(category, redact_text(text)[:300]) from exc

    async def start_session(self, language: str, vocabulary: str) -> None:
        error = self.validate_profile(self._profile)
        if error is not None:
            raise ProviderConfigurationError(error.category, error.message)
        model = self._profile.model.strip() or GEMINI_DEFAULT_MODEL
        client = GeminiLiveClient(api_key=self._profile.api_key, model=model)
        try:
            await client.connect(language=language)
        except Exception as exc:
            raise ProviderConfigurationError(ErrorCategory.NETWORK, safe_error(exc, "Gemini connect failed: ")) from exc
        self._client = client

    async def send_audio(self, pcm: bytes) -> None:
        if self._client is not None and self._client.is_connected:
            await self._client.send_audio(pcm)

    async def pump(self) -> None:
        if self._client is None:
            return
        await self._client.receive_transcript(
            on_partial=lambda text: self._on_event(TranscriptEvent.partial(text)),
            on_final=lambda text: self._on_event(TranscriptEvent.final(text)),
        )

    async def finish_turn(self, wav_bytes: bytes | None = None) -> TranscriptEvent | None:
        return None

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
