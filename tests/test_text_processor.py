import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_typing.ai.text_processor import TextProcessor


@pytest.mark.asyncio
async def test_empty_or_whitespace_returns_immediately():
    processor = TextProcessor(api_key="test-key")
    with patch("aiohttp.ClientSession.post") as mock_post:
        assert await processor.process("") == ""
        assert await processor.process("   ") == "   "
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_url_normalization_with_models_prefix():
    processor = TextProcessor(api_key="test-key", model="models/gemini-2.0-flash")
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={
            "candidates": [
                {"content": {"parts": [{"text": "Hello, world!"}]}}
            ]
        }
    )
    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.post", return_value=mock_post_cm) as mock_post:
        result = await processor.process("hello world")
        assert result == "Hello, world!"
        call_url = mock_post.call_args[0][0]
        assert "models/gemini-2.0-flash:generateContent" in call_url
        assert "models/models/" not in call_url
        assert call_url.startswith(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=test-key"
        )


@pytest.mark.asyncio
async def test_url_normalization_without_models_prefix():
    processor = TextProcessor(api_key="test-key", model="gemini-2.0-flash")
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={
            "candidates": [
                {"content": {"parts": [{"text": "Hello, world!"}]}}
            ]
        }
    )
    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.post", return_value=mock_post_cm) as mock_post:
        result = await processor.process("hello world")
        assert result == "Hello, world!"
        call_url = mock_post.call_args[0][0]
        assert "models/gemini-2.0-flash:generateContent" in call_url
        assert "models/models/" not in call_url


@pytest.mark.asyncio
async def test_fallback_on_api_error_status():
    processor = TextProcessor(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.post", return_value=mock_post_cm):
        result = await processor.process("raw transcript text")
        assert result == "raw transcript text"


@pytest.mark.asyncio
async def test_fallback_on_timeout():
    processor = TextProcessor(api_key="test-key")
    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_post_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.post", return_value=mock_post_cm):
        result = await processor.process("raw transcript text")
        assert result == "raw transcript text"


@pytest.mark.asyncio
async def test_fallback_on_empty_candidates():
    processor = TextProcessor(api_key="test-key")
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"candidates": []})
    mock_post_cm = MagicMock()
    mock_post_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_post_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.post", return_value=mock_post_cm):
        result = await processor.process("raw transcript text")
        assert result == "raw transcript text"
