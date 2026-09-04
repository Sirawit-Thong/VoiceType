# voice_typing/providers/deepgram_adapter.py
"""Deepgram live streaming adapter with interim results."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

import websockets

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

DEEPGRAM_LISTEN_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_DEFAULT_MODEL = "nova-3"

_DEEPGRAM_CAPS = ProviderCapabilities(streaming_stt=True)

ConnectFactory = Callable[[str, dict[str, str]], Awaitable[Any]]


async def _default_connect(url: str, headers: dict[str, str]):
    return await websockets.connect(url, additional_headers=headers)


def _deepgram_language(language: str) -> str:
    return {"thai": "th", "english": "en"}.get(language, "multi")


class DeepgramStreamingAdapter(SpeechProvider):
    def __init__(self, profile: ProviderProfile, on_event, connect_factory: ConnectFactory | None = None) -> None:
        super().__init__(profile, on_event)
        self._connect_factory = connect_factory or _default_connect
        self._ws = None

    @classmethod
    def capabilities_of(cls) -> ProviderCapabilities:
        return _DEEPGRAM_CAPS

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _DEEPGRAM_CAPS

    @property
    def is_session_open(self) -> bool:
        return self._ws is not None

    @classmethod
    def validate_profile(cls, profile: ProviderProfile) -> ProviderError | None:
        if not profile.api_key.strip():
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "Deepgram API key is required.")
        return None

    @classmethod
    async def list_models(cls, profile: ProviderProfile) -> list[str]:
        return []

    async def start_session(self, language: str, vocabulary: str) -> None:
        error = self.validate_profile(self._profile)
        if error is not None:
            raise ProviderConfigurationError(error.category, error.message)
        model = self._profile.model.strip() or DEEPGRAM_DEFAULT_MODEL
        query = urlencode({
            "model": model,
            "encoding": "linear16",
            "sample_rate": "16000",
            "channels": "1",
            "interim_results": "true",
            "smart_format": "true",
            "language": _deepgram_language(language),
        })
        url = f"{DEEPGRAM_LISTEN_URL}?{query}"
        headers = {"Authorization": f"Token {self._profile.api_key}"}
        try:
            self._ws = await self._connect_factory(url, headers)
        except Exception as exc:
            raise ProviderConfigurationError(ErrorCategory.NETWORK, safe_error(exc, "Deepgram connect failed: ")) from exc

    async def send_audio(self, pcm: bytes) -> None:
        if self._ws is None:
            return
        await self._ws.send(pcm)

    async def pump(self) -> None:
        if self._ws is None:
            return
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
        except TimeoutError:
            return
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        mtype = str(message.get("type", ""))
        if mtype == "Results":
            alternatives = message.get("channel", {}).get("alternatives", [{}])
            transcript = str((alternatives[0] or {}).get("transcript", ""))
            if not transcript:
                return
            if message.get("is_final"):
                self._on_event(TranscriptEvent.final(transcript))
            else:
                self._on_event(TranscriptEvent.partial(transcript))
        elif mtype == "Error":
            raw_text = str(message.get("description", message))[:300]
            detail = redact_text(raw_text)
            if self._profile.api_key:
                detail = detail.replace(self._profile.api_key, "***REDACTED***")
            if "invalid" in detail.lower() or "credential" in detail.lower():
                category = ErrorCategory.AUTHENTICATION
            else:
                category = ErrorCategory.SERVER
            self._on_event(TranscriptEvent.failure(ProviderError(category, f"Deepgram error: {detail}", False)))
        return

    async def finish_turn(self, wav_bytes: bytes | None = None) -> TranscriptEvent | None:
        return None

    async def close(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
