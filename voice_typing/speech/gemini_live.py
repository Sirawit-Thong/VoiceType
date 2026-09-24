# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import quote

import websockets
from websockets.asyncio.client import ClientConnection

from voice_typing.errors import ErrorCategory, classify_ws_error

log = logging.getLogger(__name__)

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
REST_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "models/gemini-3.1-flash-live-preview"

LANGUAGE_INSTRUCTIONS = {
    "auto": (
        "Support both Thai and English. Transcribe speech naturally in the spoken "
        "language without translation. Output ONLY Thai script or English letters — "
        "never any other script, for example Korean (Hangul), Japanese (Hiragana/"
        "Katakana), Chinese (Han), or Cyrillic. If the speech contains another "
        "language, transliterate it phonetically into Thai script. Thai has no "
        "spaces between words: never insert spaces between Thai words — use a "
        "space only after punctuation."
    ),
    "thai": (
        "Transcribe the user's speech strictly into Thai (ภาษาไทย). Do not output "
        "English or translate into English. Write pure Thai script (สระไทย) only: "
        "transliterate any non-Thai speech (English brand names, Korean, Japanese, "
        "etc.) into Thai script, and never output other scripts such as Hangul, "
        "Japanese, Chinese, or Cyrillic. Thai has no spaces between words: never "
        "insert spaces between Thai words — use a space only after punctuation."
    ),
    "english": (
        "Transcribe the user's speech strictly into English. Do not output Thai or "
        "translate into Thai. Transliterate any other language (Korean, Japanese, "
        "etc.) into English letters using the Latin alphabet. Never output Thai "
        "script or any non-Latin script. Write in English."
    ),
}


def fetch_live_models(api_key: str) -> list[str]:
    url = f"{REST_MODELS_URL}?key={quote(api_key)}&pageSize=1000"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        log.error("fetch_live_models HTTP %d: %s", exc.code, body)
        raise RuntimeError(f"API error {exc.code}: {body}") from exc
    except Exception as exc:
        log.error("fetch_live_models failed: %s", exc)
        raise
    models = data.get("models", [])
    live = sorted(
        m["name"]
        for m in models
        if "name" in m and "bidiGenerateContent" in m.get("supportedGenerationMethods", [])
    )
    if live:
        log.info("Fetched %d live-capable models", len(live))
        return live
    log.warning("No bidi-capable models found, returning all %d models", len(models))
    return sorted(m["name"] for m in models if "name" in m)


class GeminiLiveClient:
    def __init__(self, api_key: str, model: str = MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._ws: ClientConnection | None = None
        self._connected = False
        self._has_unfinalized = False
        self._last_error_category: ErrorCategory | None = None
        self._last_error_reason: str = ""

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_error_category(self) -> ErrorCategory | None:
        return self._last_error_category

    @property
    def last_error_reason(self) -> str:
        return self._last_error_reason

    async def connect(self, language: str = "auto") -> None:
        url = LIVE_API_URL
        log.info("Connecting to Gemini Live (model=%s, lang=%s) ...", self._model, language)
        try:
            self._ws = await websockets.connect(
                url,
                additional_headers={"x-goog-api-key": self._api_key},
            )
        except Exception as exc:
            category, reason = classify_ws_error(exc)
            self._last_error_category = category
            self._last_error_reason = reason
            log.error("Connect failed [%s]: %s — %s", category.value, reason, exc)
            raise
        model_name = (
            self._model
            if self._model.startswith("models/")
            else f"models/{self._model}"
        )
        lang_hint = LANGUAGE_INSTRUCTIONS.get(
            language, LANGUAGE_INSTRUCTIONS["auto"]
        )
        instruction = (
            "You are a speech-to-text transcription service. "
            "Transcribe exactly what the user says. "
            f"{lang_hint} Output only the transcription, nothing else."
        )
        setup_msg = {
            "setup": {
                "model": model_name,
                "generationConfig": {"responseModalities": ["AUDIO"]},
                "systemInstruction": {"parts": [{"text": instruction}]},
            }
        }
        await self._ws.send(json.dumps(setup_msg))
        # Wait briefly for server setup acknowledgment
        try:
            ack_raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            ack = json.loads(ack_raw)
            # Server may send setupComplete or an error
            if "error" in ack:
                raise ConnectionError(f"Server rejected setup: {ack['error']}")
        except asyncio.TimeoutError:
            log.warning("No setup acknowledgment received within 5s — proceeding anyway")
        except json.JSONDecodeError:
            log.warning("Non-JSON setup response — proceeding anyway")
        self._connected = True
        self._has_unfinalized = False
        log.info("Connected to Gemini Live ✓")

    async def send_audio(self, audio_bytes: bytes) -> None:
        if self._ws is None:
            return
        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
        msg = {
            "realtimeInput": {
                "audio": {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": b64_audio,
                }
            }
        }
        await self._ws.send(json.dumps(msg))

    async def receive_transcript(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
    ) -> None:
        if self._ws is None:
            return
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            data = json.loads(raw)
            if "serverContent" in data:
                sc = data["serverContent"]
                text = sc.get("inputTranscription", {}).get("text", "")
                turn_complete = sc.get("turnComplete", False)

                if text and not turn_complete:
                    self._has_unfinalized = True
                    on_partial(text)
                if turn_complete:
                    if text or self._has_unfinalized:
                        self._has_unfinalized = False
                        on_final(text)
                elif "modelTurn" in sc:
                    if self._has_unfinalized:
                        self._has_unfinalized = False
                        on_final("")
        except asyncio.TimeoutError:
            pass
        except Exception as exc:
            category, reason = classify_ws_error(exc)
            self._last_error_category = category
            self._last_error_reason = reason
            self._connected = False
            log.error("receive_transcript error [%s]: %s — %s", category.value, reason, exc)
            raise

    async def disconnect(self) -> None:
        if self._ws is not None:
            log.info("Disconnecting from Gemini Live")
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._connected = False
        self._has_unfinalized = False

    def abort(self) -> None:
        self._connected = False
        self._has_unfinalized = False
        ws = self._ws
        self._ws = None
        if ws is not None:
            log.debug("Aborting WebSocket connection")
            try:
                if hasattr(ws, "protocol") and hasattr(ws.protocol, "transport") and ws.protocol.transport is not None:
                    ws.protocol.transport.close()
                elif hasattr(ws, "transport") and ws.transport is not None:
                    ws.transport.close()
            except Exception:
                pass