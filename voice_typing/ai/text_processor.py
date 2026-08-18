# voice_typing/ai/text_processor.py
from __future__ import annotations

import logging

import aiohttp


class TextProcessor:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._api_key = api_key
        self._model = model

    async def process(self, text: str) -> str:
        if not text.strip():
            return text
        prompt = (
            "Fix punctuation and formatting in this transcription. "
            "Support both Thai and English. Keep the original meaning. "
            "Output only the corrected text.\n\n"
            f"Transcription: {text}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            return "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            logging.warning(
                "TextProcessor failed; returning raw text", exc_info=True
            )
        return text
