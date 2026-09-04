# tests/test_audio_wav.py
import io
import wave

import pytest

from voice_typing.providers.audio import (
    CHANNELS,
    SAMPLE_RATE,
    SAMPLE_WIDTH_BYTES,
    pcm_to_wav_bytes,
    wav_duration_sec,
)


def test_pcm_to_wav_bytes_produces_valid_wav():
    pcm = b"\x00\x01" * 1600
    wav_bytes = pcm_to_wav_bytes(pcm)
    assert wav_bytes[:4] == b"RIFF"
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnchannels() == CHANNELS
        assert wav.getframerate() == SAMPLE_RATE
        assert wav.getsampwidth() == SAMPLE_WIDTH_BYTES
        assert wav.getnframes() == 1600
        assert wav.readframes(1600) == pcm


def test_wav_duration_matches_sample_count():
    pcm = b"\x00\x00" * SAMPLE_RATE
    wav_bytes = pcm_to_wav_bytes(pcm)
    assert wav_duration_sec(wav_bytes) == pytest.approx(1.0)


def test_pcm_to_wav_bytes_rejects_empty_input():
    with pytest.raises(ValueError, match="no audio"):
        pcm_to_wav_bytes(b"")


def test_pcm_to_wav_bytes_rejects_misaligned_input():
    with pytest.raises(ValueError, match="frame-aligned"):
        pcm_to_wav_bytes(b"\x00")
