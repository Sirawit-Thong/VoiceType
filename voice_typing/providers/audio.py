"""PCM buffering helpers shared by batch STT adapters and the worker.

The recorder delivers 16-kHz mono 16-bit PCM chunks. Batch providers need
one in-memory WAV document per utterance; this module builds it.
"""
from __future__ import annotations

import io
import wave

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2


def pcm_to_wav_bytes(
    pcm: bytes,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    sample_width: int = SAMPLE_WIDTH_BYTES,
) -> bytes:
    if not pcm:
        raise ValueError("no audio captured")
    if len(pcm) % (channels * sample_width) != 0:
        raise ValueError(f"pcm length {len(pcm)} is not frame-aligned")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def wav_duration_sec(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        rate = wav.getframerate() or SAMPLE_RATE
        return wav.getnframes() / float(rate)
