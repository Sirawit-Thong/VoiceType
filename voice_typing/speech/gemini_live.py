# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import quote

import websockets
from websockets.asyncio.client import ClientConnection

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
REST_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "gemini-3.1-flash-live-preview"


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
        m["name"].removeprefix("models/")
        for m in models
        if "bidiGenerateContent" in m.get("supportedGenerationMethods", [])
    )
    if live:
        return live
    return sorted(m["name"].removeprefix("models/") for m in models)


class GeminiLiveClient:
    def __init__(self, api_key: str, model: str = MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._ws: ClientConnection | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        url = f"{LIVE_API_URL}?key={self._api_key}"
        self._ws = await websockets.connect(url)
        setup_msg = {
            "setup": {
                "model": f"models/{self._model}",
                "generationConfig": {"responseModalities": ["AUDIO"]},
                "systemInstruction": {
                    "parts": [
                        {"text": "You are a speech-to-text transcription service. Transcribe exactly what the user says. Support both Thai and English. Output only the transcription, nothing else."}
                    ]
                },
            }
        }
        await self._ws.send(json.dumps(setup_msg))
        self._connected = True

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
                if text:
                    if sc.get("turnComplete", False):
                        on_final(text)
                    else:
                        on_partial(text)
        except asyncio.TimeoutError:
            pass
        except Exception:
            self._connected = False
            raise

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected = False