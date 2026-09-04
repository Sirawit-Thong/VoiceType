# tests/test_cleanup.py
from unittest.mock import AsyncMock, patch

import pytest

from voice_typing.providers.cleanup import GeminiCleanupProvider, OpenAIChatCleanupProvider


@pytest.mark.asyncio
async def test_gemini_cleanup_returns_corrected_text():
    provider = GeminiCleanupProvider(api_key="k")
    with patch("voice_typing.providers.cleanup.TextProcessor") as factory:
        factory.return_value.process = AsyncMock(return_value="Hello, world.")
        assert await provider.cleanup("hello world", "Python") == "Hello, world."
        _kwargs = factory.call_args
        assert _kwargs.kwargs.get("vocabulary") == "Python" or _kwargs[1].get("vocabulary") == "Python"


@pytest.mark.asyncio
async def test_gemini_cleanup_falls_back_to_raw_on_failure():
    provider = GeminiCleanupProvider(api_key="k")
    with patch("voice_typing.providers.cleanup.TextProcessor") as factory:
        factory.return_value.process = AsyncMock(side_effect=RuntimeError("down"))
        assert await provider.cleanup("raw text") == "raw text"


@pytest.mark.asyncio
async def test_openai_chat_cleanup_posts_and_parses():
    calls = []

    async def fake_post(url, headers, payload, timeout_sec, verify_tls):
        calls.append({"url": url, "headers": headers, "payload": payload})
        return 200, {"choices": [{"message": {"content": "  Cleaned.  "}}]}

    provider = OpenAIChatCleanupProvider(base_url="http://localhost:1234/v1", model="m", http_post=fake_post)
    assert await provider.cleanup("messy") == "Cleaned."
    assert calls[0]["url"] == "http://localhost:1234/v1/chat/completions"
    assert calls[0]["payload"]["model"] == "m"
    assert "messy" in calls[0]["payload"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_openai_chat_cleanup_returns_raw_on_http_error():
    async def fake_post(url, headers, payload, timeout_sec, verify_tls):
        return 500, {}

    provider = OpenAIChatCleanupProvider(base_url="http://x/v1", model="m", http_post=fake_post)
    assert await provider.cleanup("keep me") == "keep me"


@pytest.mark.asyncio
async def test_openai_chat_cleanup_returns_raw_on_transport_error():
    async def fake_post(url, headers, payload, timeout_sec, verify_tls):
        raise OSError("down")

    provider = OpenAIChatCleanupProvider(base_url="http://x/v1", model="m", http_post=fake_post)
    assert await provider.cleanup("keep me") == "keep me"


def test_cleanup_prompt_mentions_vocabulary():
    from voice_typing.providers.cleanup import build_cleanup_prompt

    prompt = build_cleanup_prompt("hello", "Python, PySide6")
    assert "hello" in prompt
    assert "Python, PySide6" in prompt
