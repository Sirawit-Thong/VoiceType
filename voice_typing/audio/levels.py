# voice_typing/audio/levels.py
"""Pure audio-level helpers: vectorized RMS + smoothing curve.

Extracted from WorkerThread._update_audio_level so the hot path
(audio callback thread, every 100ms) is testable and fast.
All functions are pure except where noted.
"""
from __future__ import annotations

import numpy as np

_PCM_MAX = 32768.0
DEFAULT_SILENCE_THRESHOLD = 0.005


def rms_normalized(audio_bytes: bytes) -> float | None:
    """Return normalized RMS (0.0-~1.0) or None for invalid input.

    Pure: same bytes in -> same value out, no side effects.
    """
    if len(audio_bytes) < 2 or len(audio_bytes) % 2 != 0:
        return None
    try:
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    except (ValueError, TypeError):
        return None
    if samples.size == 0:
        return None
    mean_sq = float(np.mean(samples * samples))
    if mean_sq <= 0.0:
        return 0.0
    return float(np.sqrt(mean_sq) / _PCM_MAX)


def smooth_level(
    normalized: float,
    last_level: float,
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
) -> tuple[float, float]:
    """Apply silence gate + attack/release curve.

    Returns (emit_level, new_last_level). Pure.
    """
    if normalized < silence_threshold:
        return 0.0, last_level * 0.9
    level = max(normalized**0.5, last_level * 0.75)
    level = max(0.0, min(1.0, level))
    return level, level


def calculate_audio_level(
    audio_bytes: bytes,
    last_level: float,
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
) -> tuple[float | None, float]:
    """Compose RMS + smoothing. Returns (emit | None, new_last).

    None emit means invalid input — caller should skip Signal emit
    and leave state untouched (matches legacy early-return).
    """
    normalized = rms_normalized(audio_bytes)
    if normalized is None:
        return None, last_level
    emit, new_last = smooth_level(normalized, last_level, silence_threshold)
    return emit, new_last


def is_silence(
    audio_bytes: bytes,
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
) -> bool | None:
    """VAD gate: True=silence (skip send), False=voice, None=invalid.

    Pure: lets WorkerThread skip `send_audio` for silent chunks
    to save bandwidth + provider cost without touching state.
    """
    normalized = rms_normalized(audio_bytes)
    if normalized is None:
        return None
    return normalized < silence_threshold
