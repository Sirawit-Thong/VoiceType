import json
from unittest.mock import AsyncMock, MagicMock, call, patch

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
    assert payload["setup"]["model"] == "models/gemini-3.1-flash-live-preview"
    assert payload["setup"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert "transcribe" in payload["setup"]["systemInstruction"]["parts"][0]["text"].lower()


@pytest.mark.asyncio
async def test_send_audio_encodes_pcm():
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value="{}")
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.send_audio(b"\x00\x01\x02\x03")
    sent = json.loads(ws.send.call_args.args[0])
    audio = sent["realtimeInput"]["audio"]
    assert audio["mimeType"] == "audio/pcm;rate=16000"
    assert audio["data"] == "AAECAw=="


@pytest.mark.asyncio
async def test_connect_normalizes_bare_model_name():
    ws = AsyncMock()
    ws.recv = AsyncMock(return_value="{}")
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key", model="gemini-3.1-flash-live-preview")
        await client.connect()
    payload = json.loads(ws.send.call_args.args[0])
    assert payload["setup"]["model"] == "models/gemini-3.1-flash-live-preview"


@pytest.mark.asyncio
async def test_receive_dispatches_partial_and_final():
    ws = AsyncMock()
    partial = MagicMock()
    final = MagicMock()
    ws.recv = AsyncMock(side_effect=[
        json.dumps({"serverContent": {"inputTranscription": {"text": "hello"}, "turnComplete": False}}),
        json.dumps({"serverContent": {"modelTurn": {"parts": []}}}),
        json.dumps({"serverContent": {"inputTranscription": {"text": "hello world"}, "turnComplete": True}}),
    ])
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
    partial.assert_called_once_with("hello")
    assert final.call_args_list == [call(""), call("hello world")]
