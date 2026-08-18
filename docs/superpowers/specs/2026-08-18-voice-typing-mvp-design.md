# VoiceType MVP — Design Spec

**Date:** 2026-08-18
**Status:** Approved
**Goal:** Low-latency voice-to-text typing for Windows, supporting Thai + English mixed input

---

## Overview

VoiceType is a Windows desktop application that captures microphone audio, streams it to Gemini Live API via WebSocket for real-time speech-to-text, and injects the resulting text into the currently focused application window. The system prioritizes **low latency** and **broad application compatibility**.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| UI Framework | PySide6 |
| Audio Capture | sounddevice |
| Speech-to-Text | Gemini Live API (WebSocket bidirectional streaming) |
| Text Injection | Windows API (ctypes) — Clipboard + SendInput + UIA |
| Hotkey System | Windows API (RegisterHotKey via ctypes) |
| Clipboard | pyperclip |
| Async Runtime | asyncio + WebSocket |
| Build/Distribution | PyInstaller → .exe |

## Architecture

```text
voice_typing/
├── app.py                     # Entry point, application lifecycle
├── audio/
│   └── recorder.py            # Microphone capture, audio stream management
├── speech/
│   ├── engine.py              # STT engine interface (abstract + implementations)
│   └── gemini_live.py         # Gemini Live API WebSocket client
├── ai/
│   └── text_processor.py      # Punctuation correction, text enhancement (Smart Mode)
├── windows/
│   ├── hotkey.py              # Global hotkey registration (RegisterHotKey)
│   └── text_injector.py       # Hybrid text injection (Clipboard → SendInput → UIA)
├── ui/
│   ├── tray.py                # System tray icon and context menu
│   ├── status_bar.py          # Compact floating status bar
│   └── settings_window.py     # Full settings window with tabs
├── config/
│   └── settings.py            # Configuration management (JSON/TOML)
└── tests/
```

## Core Data Flow

### Fast Path (default)

```text
Press F9
  ↓
🎤 Start streaming audio immediately
  ↓
WebSocket ⇄ Gemini Live API
  ↓
Partial transcript (buffered, not injected)
  ↓
Final segment detected
  ↓
Transcript Buffer → finalize
  ↓
Windows Text Injection → active window
```

### Two Modes

**Push-to-Talk:**
```text
Hold F9 ────────────┐
                    │ Speaking
Release F9 ─────────┘
          ↓
      Finalize
          ↓
      Inject text
```

**Toggle:**
```text
Press F9 → start stream
     ↓
Speaking continuously
     ↓
Partial transcript displayed
     ↓
Press F9 → finalize
     ↓
Inject result
```

### Fast Mode vs Smart Mode

**Fast Mode** (skip text enhancement):
```text
🎤 → Gemini Live STT → Transcript Buffer → Windows Input
```

**Smart Mode** (with text processor):
```text
🎤 → Gemini Live STT → Transcript Buffer → Text Processor → Windows Input
```

The Text Processor (AI layer) handles punctuation, formatting, and minor corrections. It is optional and disabled in Fast Mode to minimize latency.

## Transcript Buffer

Partial transcripts from Gemini Live are buffered and NOT injected into the active window character-by-character. This prevents:
- Text flicker (injecting then replacing)
- Cursor position jumps
- Duplicate text from transcript corrections

Buffer behavior:
1. Gemini streams partial results → buffer accumulates
2. When a "final" segment is detected (sentence/phrase boundary), buffer commits
3. Committed text is injected into the active window
4. Buffer resets for next segment

## Speech: Gemini Live API

### Connection

- WebSocket bidirectional streaming to Gemini Live API
- Audio sent as raw PCM chunks (16-bit, 16kHz mono)
- Partial transcripts received in real-time
- Final transcripts marked by API

### Audio Capture

- `sounddevice` captures from default/system microphone
- 16kHz sample rate, 16-bit PCM, mono
- Buffer size tuned for low latency (~100ms chunks)

### Fallback

If Gemini Live API is unavailable or quota is exceeded:
- Batch processing mode (send complete audio, wait for result)
- Higher latency but functional as backup

## Text Injection: Hybrid + Clipboard Preservation

### Injection Order

```text
Final Text
    │
    ▼
┌──────────────────────────┐
│ 1. Clipboard + Ctrl+V    │  ← Fastest for long text
│    (with preservation)   │
└──────────┬───────────────┘
           │ fail
           ▼
┌──────────────────────────┐
│ 2. SendInput             │  ← High compatibility
│    (character by char)   │
└──────────┬───────────────┘
           │ fail
           ▼
┌──────────────────────────┐
│ 3. UI Automation (UIA)   │  ← Targeted fallback
└──────────────────────────┘
```

### Clipboard Preservation

Before injecting via clipboard:
1. Save current clipboard content
2. Set clipboard to transcript text
3. Send Ctrl+V to active window
4. Restore original clipboard content

If any error occurs during the process, attempt to restore clipboard in exception handler.

### Active Window Detection

The injector inspects the active window before choosing an injection method:
- **Standard apps** (Chrome, Word, Discord, etc.) → Clipboard + Paste
- **Apps that block paste** (some games, terminal emulators) → SendInput
- **Win32/WinForms apps** → UI Automation as targeted fallback

## UI Design

### 1. System Tray

Always running. Context menu:

```text
🎙 VoiceType
├── Start / Stop
├── Mode: Push-to-Talk
├── Mode: Toggle
├── Settings
├── Test Microphone
└── Exit
```

### 2. Compact Floating Status Bar

Appears only during recording/processing. Must NOT steal focus from active window.

States:
```text
┌──────────────────────────────────┐
│ 🟢 Ready                F9       │  ← Idle
├──────────────────────────────────┤
│ 🔴 Listening...         F9       │  ← Recording
│ วันนี้ผมต้องไป meeting...       │  ← Partial transcript
├──────────────────────────────────┤
│ ⚡ Processing...                 │  ← Post-processing
└──────────────────────────────────┘
```

The status bar is a frameless, always-on-top window positioned at bottom-center of screen (or user-configurable). It uses `Qt.WindowStaysOnTopHint` and `Qt.FramelessWindowHint`. It does NOT take keyboard focus.

### 3. Full Settings Window

Opened from tray → Settings. Tabbed layout:

```text
┌──────────────────────────────────────────┐
│ VoiceType Settings                       │
├──────────────┬───────────────────────────┤
│ General      │                           │
│ Hotkey       │   Tab Content             │
│ Speech       │                           │
│ Gemini       │   ...                     │
│ Output       │                           │
│ Advanced     │                           │
└──────────────┴───────────────────────────┘
```

**General Tab:**
- Start with Windows (checkbox)
- Show status bar (checkbox)
- Sound feedback (checkbox)

**Hotkey Tab:**
- Push-to-Tight key selector (default: F9)
- Toggle key selector (default: F9)
- Custom key binding support

**Speech Tab:**
- Language: Auto / Thai / English
- Microphone selection dropdown
- Audio input level meter

**Gemini Tab:**
- API Key input (masked)
- Model selection
- Fast Mode / Smart Mode toggle
- Test API button

**Output Tab:**
- Text injection method preference
- Clipboard fallback (checkbox)
- Typing speed (characters per second)

**Advanced Tab:**
- Latency diagnostics
- Debug log viewer
- WebSocket connection settings

## First-Run Experience

```text
Launch app
  ↓
Setup wizard appears
  ↓
Step 1: Enter Gemini API Key
  ↓
Step 2: Select Microphone
  ↓
Step 3: Choose Push-to-Talk or Toggle
  ↓
Step 4: Save & minimize to tray
```

After setup, the app lives in the system tray and is invisible until the hotkey is pressed.

## Configuration

Stored as JSON in user's AppData directory:

```text
%APPDATA%/VoiceType/
├── settings.json
└── logs/
```

Key configuration fields:
- `api_key`: Gemini API key
- `mode`: "push_to_talk" | "toggle"
- `hotkey`: Virtual key code (default: VK_F9 = 0x7E)
- `language`: "auto" | "thai" | "english"
- `fast_mode`: boolean
- `microphone_device_id`: int or null (system default)
- `show_status_bar`: boolean
- `start_with_windows`: boolean

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Gemini API key invalid | Show error in tray tooltip, prompt settings |
| No microphone detected | Block start, show error in status bar |
| WebSocket disconnection | Auto-reconnect with exponential backoff |
| Text injection fails all methods | Show error tooltip, copy to clipboard as last resort |
| Clipboard access denied | Skip clipboard method, use SendInput directly |

## Testing Strategy

- Unit tests for TranscriptBuffer, TextInjector, ConfigManager
- Integration tests for Gemini WebSocket client (mock server)
- Manual testing across target apps: Chrome, Word, Discord, LINE, Notepad
- Latency measurement: hotkey press → text appearance in target window
