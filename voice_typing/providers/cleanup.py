"""Optional punctuation/format cleanup. Cleanup never blocks dictation:
any failure returns the raw transcription so text is injected exactly once.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import aiohttp

from voice_typing.providers.contracts import TextCleanupProvider
from voice_typing.ai.text_processor import TextProcessor


def build_cleanup_prompt(text: str, vocabulary: str = "") -> str:
    vocab_hint = f" Note domain-specific vocabulary/keywords: {vocabulary}." if vocabulary else ""
    return (
        "Fix punctuation and formatting in this transcription. "
        "Support both Thai and English. Keep the original meaning."
        f"{vocab_hint} Output only the corrected text.\n\nTranscription: {text}"
    )


class GeminiCleanupProvider(TextCleanupProvider):
    def __init__(self, api_key: str, model: str = "", processor_factory=None) -> None:
        self._api_key = api_key
        self._model = model
        # NOTE: default factory resolved at call time (not here) so tests can
        # patch voice_typing.providers.cleanup.TextProcessor after constructing
        # the provider. Plan's eager `or TextProcessor` binding defeats that.
        self._factory = processor_factory

    async def cleanup(self, text: str, vocabulary: str = "") -> str:
        if not text.strip():
            return text
        try:
            factory = self._factory if self._factory is not None else TextProcessor
            processor = factory(api_key=self._api_key, model=self._model or "gemini-2.5-flash", vocabulary=vocabulary)
            result = await processor.process(text)
            return result.strip() or text
        except Exception:
            return text


JsonPost = Callable[[str, dict[str, str], dict[str, Any], float, bool], Awaitable[tuple[int, dict[str, Any]]]]


async def _default_json_post(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout_sec: float, verify_tls: bool
) -> tuple[int, dict[str, Any]]:
    connector = None if verify_tls else aiohttp.TCPConnector(ssl=False)
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            try:
                data = await resp.json()
            except Exception:
                data = {}
            return resp.status, data if isinstance(data, dict) else {}


class OpenAIChatCleanupProvider(TextCleanupProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        send_bearer_key: bool = True,
        skip_tls_verify: bool = False,
        http_post: JsonPost | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._send_bearer_key = send_bearer_key
        self._skip_tls_verify = skip_tls_verify
        self._post = http_post or _default_json_post

    async def cleanup(self, text: str, vocabulary: str = "") -> str:
        if not text.strip():
            return text
        if not self._base_url or not self._model:
            return text
        url = self._base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key and self._send_bearer_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        elif self._api_key:
            headers["x-api-key"] = self._api_key
        payload = {"model": self._model, "temperature": 0.1, "messages": [{"role": "user", "content": build_cleanup_prompt(text, vocabulary)}]}
        try:
            status, data = await self._post(url, headers, payload, 10.0, not self._skip_tls_verify)
        except Exception:
            return text
        if status != 200:
            return text
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return text
        if not isinstance(content, str):
            return text
        return content.strip() or text
