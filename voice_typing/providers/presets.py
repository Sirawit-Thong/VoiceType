"""Shipped provider presets: labels, capabilities, and safe defaults.

Presets carry no credentials and no network logic. Adapters are wired to
preset ids in registry.py; capabilities here must match the adapter that
implements each id.
"""
from __future__ import annotations

from dataclasses import dataclass

from voice_typing.providers.contracts import ProviderCapabilities


@dataclass(frozen=True)
class ProviderPreset:
    provider_id: str
    label: str
    capabilities: ProviderCapabilities
    default_model: str
    default_base_url: str
    default_transcription_path: str
    needs_api_key: bool
    help_text: str


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "gemini_live": ProviderPreset(
        provider_id="gemini_live",
        label="Gemini Live (streaming)",
        capabilities=ProviderCapabilities(streaming_stt=True, model_listing=True, text_cleanup=True),
        default_model="models/gemini-3.1-flash-live-preview",
        default_base_url="",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=True,
        help_text="Google Gemini Live WebSocket. Streams microphone audio and shows partial text while you hold the hotkey.",
    ),
    "openai_realtime": ProviderPreset(
        provider_id="openai_realtime",
        label="OpenAI Realtime (streaming)",
        capabilities=ProviderCapabilities(streaming_stt=True, batch_stt=True, text_cleanup=True),
        default_model="gpt-4o-mini-transcribe",
        default_base_url="",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=True,
        help_text="OpenAI Realtime transcription over WebSocket. Set STT mode to batch upload to fall back to the standard audio endpoint.",
    ),
    "groq": ProviderPreset(
        provider_id="groq",
        label="Groq (batch upload)",
        capabilities=ProviderCapabilities(batch_stt=True, text_cleanup=True),
        default_model="whisper-large-v3-turbo",
        default_base_url="https://api.groq.com/openai/v1",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=True,
        help_text="Fast file-upload transcription. Audio is collected while you hold the hotkey and transcribed once on release.",
    ),
    "deepgram": ProviderPreset(
        provider_id="deepgram",
        label="Deepgram (streaming)",
        capabilities=ProviderCapabilities(streaming_stt=True),
        default_model="nova-3",
        default_base_url="",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=True,
        help_text="Deepgram live WebSocket with interim results. Uses its native Token authorization header.",
    ),
    "openai_compatible": ProviderPreset(
        provider_id="openai_compatible",
        label="Custom OpenAI-compatible (batch)",
        capabilities=ProviderCapabilities(batch_stt=True, text_cleanup=True),
        default_model="",
        default_base_url="",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=False,
        help_text="Escape hatch for organization proxies or local servers. Dictation needs an endpoint that implements /audio/transcriptions.",
    ),
    "freellm": ProviderPreset(
        provider_id="freellm",
        label="FreeLLM (OpenAI-compatible preset)",
        capabilities=ProviderCapabilities(batch_stt=True, text_cleanup=True),
        default_model="",
        default_base_url="",
        default_transcription_path="/audio/transcriptions",
        needs_api_key=False,
        help_text="Editable OpenAI-compatible preset. Enter the endpoint your FreeLLM service documents; chat-only servers stay available for text cleanup only.",
    ),
}

PROVIDER_ORDER = ("gemini_live", "openai_realtime", "groq", "deepgram", "openai_compatible", "freellm")
