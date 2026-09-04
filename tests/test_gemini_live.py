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


@pytest.mark.asyncio
async def test_receive_ignores_redundant_model_turn_and_turn_complete():
    ws = AsyncMock()
    partial = MagicMock()
    final = MagicMock()
    ws.recv = AsyncMock(side_effect=[
        json.dumps({"serverContent": {"inputTranscription": {"text": "hello"}, "turnComplete": False}}),
        json.dumps({"serverContent": {"modelTurn": {"parts": []}}}),
        json.dumps({"serverContent": {"modelTurn": {"parts": []}}}),  # Redundant modelTurn
        json.dumps({"serverContent": {"turnComplete": True}}),         # turnComplete with no text after finalized
    ])
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
        await client.receive_transcript(on_partial=partial, on_final=final)
    partial.assert_called_once_with("hello")
    # on_final should only be called once with "" when first modelTurn finalized the turn
    assert final.call_args_list == [call("")]


@pytest.mark.asyncio
async def test_receive_handles_turn_complete_with_text():
    ws = AsyncMock()
    partial = MagicMock()
    final = MagicMock()
    ws.recv = AsyncMock(side_effect=[
        json.dumps({"serverContent": {"inputTranscription": {"text": "direct final text"}, "turnComplete": True}}),
    ])
    with patch("voice_typing.speech.gemini_live.websockets.connect", new=AsyncMock(return_value=ws)):
        client = GeminiLiveClient(api_key="test-key")
        await client.connect()
        await client.receive_transcript(on_partial=partial, on_final=final)
    partial.assert_not_called()
    assert final.call_args_list == [call("direct final text")]


def test_fetch_live_models_filters_bidi():
    from voice_typing.speech.gemini_live import fetch_live_models

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "models": [
            {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.0-flash-exp", "supportedGenerationMethods": ["bidiGenerateContent", "generateContent"]},
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["bidiGenerateContent"]},
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = fetch_live_models(api_key="test-key")
        assert result == ["models/gemini-2.0-flash-exp", "models/gemini-2.5-flash"]


def test_fetch_live_models_fallback_when_no_bidi():
    from voice_typing.speech.gemini_live import fetch_live_models

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "models": [
            {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
        ]
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = fetch_live_models(api_key="test-key")
        assert result == ["models/gemini-1.5-pro", "models/gemini-2.0-flash"]


def test_fetch_live_models_http_error():
    import urllib.error

    from voice_typing.speech.gemini_live import fetch_live_models

    error = urllib.error.HTTPError(
        url="https://generativelanguage.googleapis.com",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": "API key invalid"}'),
    )

    with patch("urllib.request.urlopen", side_effect=error), pytest.raises(RuntimeError, match="API error 403"):
        fetch_live_models(api_key="invalid-key")

