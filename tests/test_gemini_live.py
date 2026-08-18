import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_typing.speech.gemini_live import GeminiLiveClient


def test_client_initial_state():
    client = GeminiLiveClient(api_key="test-key")
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_connect_sends_setup_message():
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value="{}")
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
    sent = ws.send.call_args.args[0]
    payload = json.loads(sent)
    assert payload["setup"]["model"] == "models/gemini-2.0-flash-live-001"
    assert payload["setup"]["generation_config"]["response_modalities"] == ["TEXT"]
    assert "transcribe" in payload["setup"]["system_instruction"]["parts"][0]["text"].lower()


@pytest.mark.asyncio
async def test_send_audio_encodes_pcm():
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value="{}")
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.send_audio(b"\x00\x01\x02\x03")
    sent = json.loads(ws.send.call_args.args[0])
    chunk = sent["realtimeInput"]["mediaChunks"][0]
    assert chunk["mimeType"] == "audio/pcm;rate=16000"
    assert chunk["data"] == "AAECAw=="


@pytest.mark.asyncio
async def test_receive_dispatches_partial_and_final():
    ws = AsyncMock()
    partial = MagicMock()
    final = MagicMock()
    ws.recv = AsyncMock(side_effect=[
        json.dumps({"serverContent": {"modelTurn": {"parts": [{"text": "hello"}]}, "turnComplete": False}}),
        json.dumps({"serverContent": {"modelTurn": {"parts": [{"text": "hello world"}]}, "turnComplete": True}}),
    ])
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
    partial.assert_called_once_with("hello")
    final.assert_called_once_with("hello world")
