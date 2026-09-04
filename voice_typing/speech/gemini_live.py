# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import quote

import websockets
from websockets.asyncio.client import ClientConnection

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
REST_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "models/gemini-3.1-flash-live-preview"

LANGUAGE_INSTRUCTIONS = {
    "auto": "Support both Thai and English. Transcribe speech naturally in the spoken language without translation.",
    "thai": "Transcribe the user's speech strictly into Thai (ภาษาไทย). Do not output English or translate into English. Write pure Thai script.",
    "english": "Transcribe the user's speech strictly into English. Do not output Thai or translate into Thai. Write in English.",
}


def fetch_live_models(api_key: str) -> list[str]:
    url = f"{REST_MODELS_URL}?key={quote(api_key)}&pageSize=1000"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"API error {exc.code}: {body}") from exc
    models = data.get("models", [])
    live = sorted(
        m["name"]
        for m in models
        if "name" in m and "bidiGenerateContent" in m.get("supportedGenerationMethods", [])
    )
    if live:
        return live
    return sorted(m["name"] for m in models if "name" in m)


class GeminiLiveClient:
    def __init__(self, api_key: str, model: str = MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._ws: ClientConnection | None = None
        self._connected = False
        self._has_unfinalized = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, language: str = "auto") -> None:
        url = f"{LIVE_API_URL}?key={self._api_key}"
        self._ws = await websockets.connect(url)
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
        self._connected = True
        self._has_unfinalized = False

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
                if turn_complete and (text or self._has_unfinalized):
                    self._has_unfinalized = False
                    on_final(text)
                elif "modelTurn" in sc:
                    if self._has_unfinalized:
                        self._has_unfinalized = False
                        on_final("")
        except TimeoutError:
            pass
        except Exception:
            self._connected = False
            raise

    async def disconnect(self) -> None:
        if self._ws is not None:
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
            try:
                if hasattr(ws, "protocol") and hasattr(ws.protocol, "transport") and ws.protocol.transport is not None:
                    ws.protocol.transport.close()
                elif hasattr(ws, "transport") and ws.transport is not None:
                    ws.transport.close()
            except Exception:
                pass
