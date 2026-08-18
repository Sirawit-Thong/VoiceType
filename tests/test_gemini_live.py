# tests/test_gemini_live.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from voice_typing.speech.gemini_live import GeminiLiveClient


def test_client_initial_state():
    client = GeminiLiveClient(api_key="test-key")
    assert client.is_connected is False