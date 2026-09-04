# voice_typing/providers/openai_realtime.py
"""OpenAI Realtime transcription adapter with batch-upload fallback.

Streaming mode talks to the Realtime WebSocket. When the profile STT mode
is "batch", the adapter delegates finish_turn to OpenAITranscriptionAdapter
so one provider id covers both transports.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, Awaitable, Callable
from urllib.parse import quote

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
from voice_typing.providers.openai_batch import HttpPost, OpenAITranscriptionAdapter
from voice_typing.providers.redaction import redact_text, safe_error

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
OPENAI_REALTIME_MODEL = "gpt-4o-mini-transcribe"

_REALTIME_CAPS = ProviderCapabilities(streaming_stt=True, batch_stt=True, text_cleanup=True)

ConnectFactory = Callable[[str, dict[str, str]], Awaitable[Any]]


async def _default_connect(url: str, headers: dict[str, str]):
    return await websockets.connect(url, additional_headers=headers)


def _openai_language(language: str) -> str | None:
    return {"thai": "th", "english": "en"}.get(language)


class OpenAIRealtimeAdapter(SpeechProvider):
    def __init__(
        self,
        profile: ProviderProfile,
        on_event,
        connect_factory: ConnectFactory | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        super().__init__(profile, on_event)
        self._connect_factory = connect_factory or _default_connect
        self._http_post = http_post
        self._ws = None
        self._delegate: OpenAITranscriptionAdapter | None = None
        self._language = "auto"

    @classmethod
    def capabilities_of(cls) -> ProviderCapabilities:
        return _REALTIME_CAPS

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _REALTIME_CAPS

    @property
    def is_session_open(self) -> bool:
        return self._ws is not None or self._delegate is not None

    @classmethod
    def validate_profile(cls, profile: ProviderProfile) -> ProviderError | None:
        if not profile.api_key.strip():
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, "OpenAI API key is required.")
        if profile.stt_mode not in ("default", "realtime", "batch"):
            return ProviderError(ErrorCategory.INVALID_CONFIGURATION, f"Unknown STT mode '{profile.stt_mode}'.")
        return None

    @classmethod
    async def list_models(cls, profile: ProviderProfile) -> list[str]:
        return []

    def _is_batch(self) -> bool:
        return self._profile.stt_mode == "batch"

    async def start_session(self, language: str, vocabulary: str) -> None:
        error = self.validate_profile(self._profile)
        if error is not None:
            raise ProviderConfigurationError(error.category, error.message)
        self._language = language
        if self._is_batch():
            self._delegate = OpenAITranscriptionAdapter(self._profile, self._on_event, http_post=self._http_post)
            await self._delegate.start_session(language, vocabulary)
            return
        model = self._profile.model.strip() or OPENAI_REALTIME_MODEL
        url = f"{OPENAI_REALTIME_URL}?model={quote(model)}&intent=transcription"
        headers = {"Authorization": f"Bearer {self._profile.api_key}", "OpenAI-Beta": "realtime=v1"}
        try:
            self._ws = await self._connect_factory(url, headers)
        except Exception as exc:
            raise ProviderConfigurationError(ErrorCategory.NETWORK, safe_error(exc, "OpenAI Realtime connect failed: ")) from exc
        session: dict[str, Any] = {
            "input_audio_format": "pcm16",
            "input_audio_transcription": {"model": model},
        }
        lang = _openai_language(language)
        if lang is not None:
            session["input_audio_transcription"]["language"] = lang
        await self._ws.send(json.dumps({"type": "transcription_session.update", "session": session}))

    async def send_audio(self, pcm: bytes) -> None:
        if self._delegate is not None:
            return None
        if self._ws is None:
            return None
        await self._ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")}))

    async def pump(self) -> None:
        if self._delegate is not None or self._ws is None:
            return None
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
        except asyncio.TimeoutError:
            return None
        try:
            message = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(message, dict):
            return None
        mtype = str(message.get("type", ""))
        if mtype.endswith("transcription.delta"):
            delta = str(message.get("delta", ""))
            if delta:
                self._on_event(TranscriptEvent.partial(delta))
        elif mtype.endswith(("transcription.done", "transcription.completed")):
            self._on_event(TranscriptEvent.final(str(message.get("transcript", ""))))
        elif mtype == "error":
            detail = message.get("error", {})
            if isinstance(detail, dict):
                raw_text = str(detail.get("message", detail))[:300]
                code = str(detail.get("code", ""))
            else:
                raw_text = str(detail)[:300]
                code = ""
            text = redact_text(raw_text)
            if self._profile.api_key:
                text = text.replace(self._profile.api_key, "***REDACTED***")
            lowered = code.lower()
            if "invalid" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
                category = ErrorCategory.AUTHENTICATION
            else:
                category = ErrorCategory.SERVER
            self._on_event(TranscriptEvent.failure(ProviderError(category, f"OpenAI Realtime error: {text}", False)))
        return None

    async def finish_turn(self, wav_bytes: bytes | None = None) -> TranscriptEvent | None:
        if self._delegate is not None:
            return await self._delegate.finish_turn(wav_bytes)
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            except Exception:
                pass
        return None

    async def close(self) -> None:
        if self._delegate is not None:
            await self._delegate.close()
            self._delegate = None
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
