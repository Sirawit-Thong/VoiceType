# voice_typing/ai/text_processor.py
from __future__ import annotations

import logging

import aiohttp


class TextProcessor:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        vocabulary: str = "",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._vocabulary = vocabulary

    async def process(self, text: str) -> str:
        if not text.strip():
            return text
        vocab_hint = (
            f" Note domain-specific vocabulary/keywords: {self._vocabulary}."
            if self._vocabulary
            else ""
        )
        prompt = (
            "Fix punctuation and formatting in this transcription. "
            "Support both Thai and English. Keep the original meaning."
            f"{vocab_hint} "
            "Output only the corrected text.\n\n"
            f"Transcription: {text}"
        )
        # Ensure we use a valid text generation model (not a live WebSocket bidi model)
        clean_model = (self._model or "").removeprefix("models/").strip()
        if not clean_model or "live" in clean_model.lower() or "bidi" in clean_model.lower():
            model_name = "gemini-2.5-flash"
        else:
            model_name = clean_model

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            result = "".join(p.get("text", "") for p in parts).strip()
                            if result:
                                return result
                    elif resp.status == 404 and model_name != "gemini-1.5-flash":
                        # Try fallback model
                        fb_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self._api_key}"
                        async with session.post(
                            fb_url,
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as fb_resp:
                            if fb_resp.status == 200:
                                fb_data = await fb_resp.json()
                                fb_cands = fb_data.get("candidates", [])
                                if fb_cands:
                                    fb_parts = fb_cands[0].get("content", {}).get("parts", [])
                                    fb_result = "".join(p.get("text", "") for p in fb_parts).strip()
                                    if fb_result:
                                        return fb_result
                            logging.debug("TextProcessor fallback returned HTTP %s", fb_resp.status)
                    else:
                        logging.debug(
                            "TextProcessor API returned HTTP %s for model %s", resp.status, model_name
                        )
        except Exception:
            logging.debug(
                "TextProcessor failed; returning raw text", exc_info=True
            )
        return text

