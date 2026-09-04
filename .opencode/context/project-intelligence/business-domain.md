<!-- Context: project-intelligence/business | Priority: high | Version: 1.0 | Updated: 2026-09-04 -->

# VoiceType Business Domain

> Low-latency voice-to-text typing for Windows — speak anywhere, text appears in the active app.

## Problem

Typing is slow for Thai/English switchers, developers dictating notes, and users with typing difficulties. Existing dictation tools are high-latency, English-centric, or locked to one vendor.

## Users

| User | Need |
|------|------|
| Thai professionals | Pure-Thai output, no English phonetic mixing; instant Thai/English switch |
| Developers | Dictate into VS Code, Discord, browsers without switching windows |
| Accessibility users | Hands-free typing in any Windows app (Word, Line, Notion) |

## Value Proposition

- **Sub-second partial results** via streaming STT; Fast Mode injects text with zero latency
- **Strict Thai / English / Auto modes** + custom vocabulary for domain terms
- **Vendor freedom**: Gemini Live, OpenAI, Groq, Deepgram, FreeLLM, any OpenAI-compatible endpoint
- **Push-to-talk or toggle** with mouse side buttons, middle click, or keyboard hotkeys

## Scope Boundaries

- Windows 10/11 64-bit only; no macOS/Linux client
- API keys belong to the user (BYOK) — stored in Windows Credential Manager, never on our servers (there are none)
- `docs/` plans are working notes, never shipped

## 📂 Codebase References

**Features**: `README.md` (Features, Quick Start) · **Languages/UI**: `voice_typing/ui/settings_window.py`, `voice_typing/ui/status_bar.py` · **Triggers**: `voice_typing/windows/hotkey.py`

## Related Files

- `technical-domain.md` — how it's built
- `business-tech-bridge.md` — needs → solutions mapping
