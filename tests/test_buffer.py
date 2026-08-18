# tests/test_buffer.py
from voice_typing.speech.engine import TranscriptBuffer


def test_buffer_accumulates_partials():
    buf = TranscriptBuffer()
    buf.add_partial("hello")
    buf.add_partial("hello world")
    assert buf.current == "hello world"


def test_buffer_finalize_returns_and_resets():
    buf = TranscriptBuffer()
    buf.add_partial("hello world")
    result = buf.finalize()
    assert result == "hello world"
    assert buf.current == ""


def test_buffer_finalize_empty():
    buf = TranscriptBuffer()
    result = buf.finalize()
    assert result == ""


def test_buffer_reset():
    buf = TranscriptBuffer()
    buf.add_partial("some text")
    buf.reset()
    assert buf.current == ""