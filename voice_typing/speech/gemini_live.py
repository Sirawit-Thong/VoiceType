# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
from typing import Callable

import websockets
from websockets.asyncio.client import ClientConnection

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
MODEL = "gemini-3.1-flash-live-preview"


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
                "mediaChunks": [
                    {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": b64_audio,
                    }
                ]
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

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected = False