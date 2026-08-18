# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
from typing import Callable

import websockets
from websockets.asyncio.client import ClientConnection

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
MODEL = "gemini-2.0-flash-live-001"


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
        url = f"{LIVE_API_URL}?model=models/{self._model}&key={self._api_key}"
        self._ws = await websockets.connect(url)
        setup_msg = {
            "setup": {
                "model": f"models/{self._model}",
                "generation_config": {
                    "response_modalities": ["TEXT"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {"voice_name": "Aoede"}
                        }
                    },
                },
                "system_instruction": {
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
                parts = (
                    data["serverContent"]
                    .get("modelTurn", {})
                    .get("parts", [])
                )
                text = "".join(p.get("text", "") for p in parts)
                if text:
                    is_turn_complete = data["serverContent"].get(
                        "turnComplete", False
                    )
                    if is_turn_complete:
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