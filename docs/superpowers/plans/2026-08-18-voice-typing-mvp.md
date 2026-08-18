# VoiceType MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a low-latency voice-to-text Windows desktop app using Python, PySide6, Gemini Live API WebSocket streaming, and hybrid text injection.

**Architecture:** Push-to-talk/toggle hotkey triggers microphone audio capture → streamed to Gemini Live API via WebSocket → partial transcripts buffered → finalized text injected into active window via clipboard+paste with SendInput/UIA fallback. System tray app with floating status bar.

**Tech Stack:** Python 3.12+, PySide6, sounddevice, websockets, Gemini Live API, ctypes (Win32), pyperclip, PyInstaller

**Spec:** `docs/superpowers/specs/2026-08-18-voice-typing-mvp-design.md`

## Global Constraints

- Python 3.12+ minimum
- Windows only (Win32 API for hotkeys, text injection)
- PySide6 for all UI components
- Gemini Live API for speech-to-text (WebSocket bidirectional streaming)
- Audio: 16kHz, 16-bit PCM, mono via sounddevice
- Config stored in `%APPDATA%/VoiceType/settings.json`
- Tests via pytest
- No external comment blocks unless requested

## File Structure

```
voice_typing/
├── app.py                     # Entry point, Qt event loop, wiring
├── __init__.py
├── audio/
│   ├── __init__.py
│   └── recorder.py            # Microphone capture via sounddevice
├── speech/
│   ├── __init__.py
│   ├── engine.py              # Abstract STT engine interface
│   └── gemini_live.py         # Gemini Live API WebSocket client
├── ai/
│   ├── __init__.py
│   └── text_processor.py      # Punctuation/formatting enhancement (Smart Mode)
├── windows/
│   ├── __init__.py
│   ├── hotkey.py              # Global hotkey via RegisterHotKey
│   └── text_injector.py       # Hybrid: Clipboard → SendInput → UIA
├── ui/
│   ├── __init__.py
│   ├── tray.py                # System tray icon + context menu
│   ├── status_bar.py          # Floating status bar (no focus steal)
│   └── settings_window.py     # Tabbed settings dialog
├── config/
│   ├── __init__.py
│   └── settings.py            # JSON config management
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_recorder.py
    ├── test_buffer.py
    ├── test_text_injector.py
    ├── test_gemini_live.py
    └── test_app.py
```

---

### Task 1: Project Scaffolding + Config Manager

**Files:**
- Create: `voice_typing/__init__.py`
- Create: `voice_typing/config/__init__.py`
- Create: `voice_typing/config/settings.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`
- Create: `pyproject.toml`

**Interfaces:**
- Produces: `SettingsManager` class with `load()`, `save()`, `get()`, `set()` methods

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "voicetype"
version = "0.1.0"
description = "Low-latency voice-to-text typing for Windows"
requires-python = ">=3.12"
dependencies = [
    "PySide6>=6.6.0",
    "sounddevice>=0.4.6",
    "websockets>=12.0",
    "pyperclip>=1.8.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create directory structure**

Create all `__init__.py` files (empty) for: `voice_typing/`, `voice_typing/config/`, `voice_typing/audio/`, `voice_typing/speech/`, `voice_typing/ai/`, `voice_typing/windows/`, `voice_typing/ui/`, `tests/`

- [ ] **Step 3: Write the failing test for SettingsManager**

```python
# tests/test_config.py
import json
import os
from pathlib import Path

from voice_typing.config.settings import SettingsManager


def test_settings_load_creates_default(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mode"] == "push_to_talk"
    assert data["hotkey"] == 0x7E
    assert data["fast_mode"] is True


def test_settings_set_and_get(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    mgr.set("api_key", "test-key-123")
    mgr.save()
    mgr2 = SettingsManager(config_path)
    mgr2.load()
    assert mgr2.get("api_key") == "test-key-123"


def test_settings_get_default(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get("nonexistent_key", "fallback") == "fallback"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voice_typing.config.settings'`

- [ ] **Step 5: Implement SettingsManager**

```python
# voice_typing/config/settings.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "mode": "push_to_talk",
    "hotkey": 0x7E,
    "language": "auto",
    "fast_mode": True,
    "microphone_device_id": None,
    "show_status_bar": True,
    "start_with_windows": False,
    "sound_feedback": True,
    "typing_speed": 0,
}


class SettingsManager:
    def __init__(self, config_path: Path | str) -> None:
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}

    def load(self) -> None:
        if self._path.exists():
            raw = self._path.read_text(encoding="utf-8")
            self._data = json.loads(raw)
        else:
            self._data = dict(DEFAULT_SETTINGS)
            self.save()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd D:\dev\TT && python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add voice_typing/ tests/ pyproject.toml
git commit -m "feat: project scaffolding and config manager"
```

---

### Task 2: Audio Recorder

**Files:**
- Create: `voice_typing/audio/__init__.py`
- Create: `voice_typing/audio/recorder.py`
- Create: `tests/test_recorder.py`

**Interfaces:**
- Produces: `AudioRecorder` class — `start(callback)`, `stop()`, `is_recording` property
- Callback signature: `callback(audio_bytes: bytes) -> None` — called with PCM chunks

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recorder.py
from unittest.mock import MagicMock, patch

from voice_typing.audio.recorder import AudioRecorder


def test_recorder_initial_state():
    rec = AudioRecorder()
    assert rec.is_recording is False


@patch("voice_typing.audio.recorder.sd")
def test_recorder_start_stop(mock_sd):
    rec = AudioRecorder()
    cb = MagicMock()
    rec.start(callback=cb)
    assert rec.is_recording is True
    mock_sd.InputStream.assert_called_once()
    rec.stop()
    assert rec.is_recording is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement AudioRecorder**

```python
# voice_typing/audio/recorder.py
from __future__ import annotations

from typing import Callable

import sounddevice as sd
import numpy as np


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_DURATION_MS = 100
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)


class AudioRecorder:
    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._callback: Callable[[bytes], None] | None = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if self._callback is not None:
            pcm_bytes = indata.tobytes()
            self._callback(pcm_bytes)

    def start(self, callback: Callable[[bytes], None]) -> None:
        if self._is_recording:
            return
        self._callback = callback
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._is_recording = True

    def stop(self) -> None:
        if not self._is_recording:
            return
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._is_recording = False
        self._callback = None
```

- [ ] **Step 4: Run tests**

Run: `cd D:\dev\TT && python -m pytest tests/test_recorder.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add voice_typing/audio/ tests/test_recorder.py
git commit -m "feat: audio recorder with sounddevice"
```

---

### Task 3: Global Hotkey System

**Files:**
- Create: `voice_typing/windows/__init__.py`
- Create: `voice_typing/windows/hotkey.py`
- Create: `tests/test_hotkey.py`

**Interfaces:**
- Produces: `HotkeyManager` class — `register(vk_code, callback)`, `unregister(vk_code)`, `start()`, `stop()`
- Callback signature: `callback(vk_code: int) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hotkey.py
from unittest.mock import MagicMock

from voice_typing.windows.hotkey import HotkeyManager


def test_hotkey_initial_state():
    mgr = HotkeyManager()
    assert mgr.is_running is False


def test_hotkey_register_unregister():
    mgr = HotkeyManager()
    cb = MagicMock()
    mgr.register(0x7E, cb)
    assert 0x7E in mgr._hotkeys
    mgr.unregister(0x7E)
    assert 0x7E not in mgr._hotkeys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_hotkey.py -v`
Expected: FAIL

- [ ] **Step 3: Implement HotkeyManager**

```python
# voice_typing/windows/hotkey.py
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import threading
from typing import Callable

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
MOD_NONE = 0x0000


class HotkeyManager:
    def __init__(self) -> None:
        self._hotkeys: dict[int, Callable[[int], None]] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._hwnd: int | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def register(self, vk_code: int, callback: Callable[[int], None]) -> None:
        self._hotkeys[vk_code] = callback

    def unregister(self, vk_code: int) -> None:
        self._hotkeys.pop(vk_code, None)

    def _message_loop(self) -> None:
        msg = wintypes.MSG()
        while self._running:
            b = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if b == 0 or b == -1:
                break
            if msg.message == WM_HOTKEY:
                vk = msg.wParam & 0xFFFFFFFF
                cb = self._hotkeys.get(vk)
                if cb is not None:
                    cb(vk)

    def start(self) -> None:
        if self._running:
            return
        for vk in self._hotkeys:
            user32.RegisterHotKey(None, vk, MOD_NONE, vk)
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for vk in self._hotkeys:
            user32.UnregisterHotKey(None, vk)
        if self._hwnd is not None:
            user32.PostMessageW(self._hwnd, 0x0012, 0, 0)
```

- [ ] **Step 4: Run tests**

Run: `cd D:\dev\TT && python -m pytest tests/test_hotkey.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add voice_typing/windows/ tests/test_hotkey.py
git commit -m "feat: global hotkey manager via Win32 RegisterHotKey"
```

---

### Task 4: Transcript Buffer

**Files:**
- Create: `voice_typing/speech/__init__.py`
- Create: `voice_typing/speech/engine.py`
- Create: `tests/test_buffer.py`

**Interfaces:**
- Produces: `TranscriptBuffer` class — `add_partial(text)`, `finalize() -> str`, `reset()`
- Produces: `STTEngine` abstract base class

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_buffer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TranscriptBuffer + STTEngine ABC**

```python
# voice_typing/speech/engine.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class TranscriptBuffer:
    def __init__(self) -> None:
        self._current = ""

    @property
    def current(self) -> str:
        return self._current

    def add_partial(self, text: str) -> None:
        self._current = text

    def finalize(self) -> str:
        result = self._current
        self._current = ""
        return result

    def reset(self) -> None:
        self._current = ""


class STTEngine(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_audio(self, audio_bytes: bytes) -> None: ...

    @abstractmethod
    async def receive_transcript(
        self, on_partial: Callable[[str], None], on_final: Callable[[str], None]
    ) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
```

- [ ] **Step 4: Run tests**

Run: `cd D:\dev\TT && python -m pytest tests/test_buffer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add voice_typing/speech/ tests/test_buffer.py
git commit -m "feat: transcript buffer and STT engine interface"
```

---

### Task 5: Gemini Live API Client

**Files:**
- Create: `voice_typing/speech/gemini_live.py`
- Create: `tests/test_gemini_live.py`

**Interfaces:**
- Consumes: `STTEngine` interface from Task 4
- Produces: `GeminiLiveClient` — connects via WebSocket, sends audio, receives transcripts

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gemini_live.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from voice_typing.speech.gemini_live import GeminiLiveClient


def test_client_initial_state():
    client = GeminiLiveClient(api_key="test-key")
    assert client.is_connected is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_gemini_live.py -v`
Expected: FAIL

- [ ] **Step 3: Implement GeminiLiveClient**

```python
# voice_typing/speech/gemini_live.py
from __future__ import annotations

import asyncio
import base64
import json
from typing import Callable

import websockets

LIVE_API_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
MODEL = "gemini-2.0-flash-live-001"


class GeminiLiveClient:
    def __init__(self, api_key: str, model: str = MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        url = f"{LIVE_API_URL}?model=models/{self._model}&key={self._api_key}"
        self._ws = await websockets.connect(url)
        self._connected = True
        setup_msg = {
            "setup": {
                "model": f"models/{self._model}",
                "generation_config": {
                    "response_modalities": ["TEXT"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {"voice_name": "Aoede"}
                        }
                    },
                },
                "system_instruction": {
                    "parts": [
                        {"text": "You are a speech-to-text transcription service. Transcribe exactly what the user says. Support both Thai and English. Output only the transcription, nothing else."}
                    ]
                },
            }
        }
        await self._ws.send(json.dumps(setup_msg))

    async def send_audio(self, audio_bytes: bytes) -> None:
        if self._ws is None:
            return
        b64_audio = base64.b64encode(audio_bytes).decode("ascii")
        msg = {
            "realtimeInput": {
                "mediaChunks": [
                    {
                        "mimeType": "audio/pcm;rate=16000",
                        "data": b64_audio,
                    }
                ]
            }
        }
        await self._ws.send(json.dumps(msg))

    async def receive_transcript(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
    ) -> None:
        if self._ws is None:
            return
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            data = json.loads(raw)
            if "serverContent" in data:
                parts = (
                    data["serverContent"]
                    .get("modelTurn", {})
                    .get("parts", [])
                )
                text = "".join(p.get("text", "") for p in parts)
                if text:
                    is_turn_complete = data["serverContent"].get(
                        "turnComplete", False
                    )
                    if is_turn_complete:
                        on_final(text)
                    else:
                        on_partial(text)
        except asyncio.TimeoutError:
            pass

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        self._connected = False
```

- [ ] **Step 4: Run tests**

Run: `cd D:\dev\TT && python -m pytest tests/test_gemini_live.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add voice_typing/speech/gemini_live.py tests/test_gemini_live.py
git commit -m "feat: Gemini Live API WebSocket client"
```

---

### Task 6: Text Injector (Hybrid)

**Files:**
- Create: `voice_typing/windows/text_injector.py`
- Create: `tests/test_text_injector.py`

**Interfaces:**
- Produces: `TextInjector` class — `inject(text: str) -> bool`
- Uses clipboard preservation internally

- [ ] **Step 1: Write the failing test**

```python
# tests/test_text_injector.py
from unittest.mock import patch, MagicMock
from voice_typing.windows.text_injector import TextInjector


def test_injector_initialization():
    injector = TextInjector()
    assert injector is not None


@patch("voice_typing.windows.text_injector.pyperclip")
def test_clipboard_preservation(mock_pyperclip):
    mock_pyperclip.paste.return_value = "original text"
    injector = TextInjector()
    result = injector._clipboard_inject("new text")
    assert result is True
    mock_pyperclip.copy.assert_any_call("new text")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:\dev\TT && python -m pytest tests/test_text_injector.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TextInjector**

```python
# voice_typing/windows/text_injector.py
from __future__ import annotations

import ctypes
import time

import pyperclip

user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


def _send_key_down(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)


def _send_key_up(vk: int) -> None:
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


class TextInjector:
    def inject(self, text: str) -> bool:
        if self._clipboard_inject(text):
            return True
        if self._sendinput_inject(text):
            return True
        return False

    def _clipboard_inject(self, text: str) -> bool:
        try:
            original = pyperclip.paste()
        except Exception:
            original = ""
        try:
            pyperclip.copy(text)
            time.sleep(0.02)
            _send_key_down(VK_CONTROL)
            _send_key_down(VK_V)
            time.sleep(0.01)
            _send_key_up(VK_V)
            _send_key_up(VK_CONTROL)
            time.sleep(0.02)
            return True
        except Exception:
            return False
        finally:
            try:
                if original:
                    pyperclip.copy(original)
            except Exception:
                pass

    def _sendinput_inject(self, text: str) -> bool:
        try:
            for char in text:
                for vk, sc in _char_to_vk_sc(char):
                    _send_key_down(vk)
                    time.sleep(0.001)
                    _send_key_up(vk)
                    time.sleep(0.001)
            return True
        except Exception:
            return False


def _char_to_vk_sc(char: str) -> list[tuple[int, int]]:
    vk = user32.VkKeyScanW(ord(char)) & 0xFF
    sc = user32.MapVirtualKeyW(vk, 0)
    shift = (user32.VkKeyScanW(ord(char)) >> 8) & 0xFF
    result = []
    if shift & 0x01:
        result.append((0x10, 0))
    result.append((vk, sc))
    return result
```

- [ ] **Step 4: Run tests**

Run: `cd D:\dev\TT && python -m pytest tests/test_text_injector.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add voice_typing/windows/text_injector.py tests/test_text_injector.py
git commit -m "feat: hybrid text injector with clipboard preservation"
```

---

### Task 7: System Tray UI

**Files:**
- Create: `voice_typing/ui/__init__.py`
- Create: `voice_typing/ui/tray.py`

**Interfaces:**
- Consumes: `HotkeyManager` from Task 3
- Produces: `TrayIcon` class — `show()`, `hide()`, signals for start/stop/settings

- [ ] **Step 1: Implement TrayIcon**

```python
# voice_typing/ui/tray.py
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TraySignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    mode_changed = Signal(str)


class TrayIcon:
    def __init__(self) -> None:
        self.signals = TraySignals()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._mode: str = "push_to_talk"
        self._recording: bool = False

    def show(self) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(QIcon.fromTheme("audio-input-microphone"))
        self._tray.setToolTip("VoiceType - Ready")
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self) -> None:
        if self._menu is None:
            return
        self._menu.clear()
        if self._recording:
            action = QAction("Stop Recording")
            action.triggered.connect(self.signals.stop_recording.emit)
        else:
            action = QAction("Start Recording")
            action.triggered.connect(self.signals.start_recording.emit)
        self._menu.addAction(action)

        mode_menu = self._menu.addMenu("Mode")
        ptt_action = QAction("Push-to-Talk")
        ptt_action.setCheckable(True)
        ptt_action.setChecked(self._mode == "push_to_talk")
        ptt_action.triggered.connect(lambda: self._set_mode("push_to_talk"))
        mode_menu.addAction(ptt_action)

        toggle_action = QAction("Toggle")
        toggle_action.setCheckable(True)
        toggle_action.setChecked(self._mode == "toggle")
        toggle_action.triggered.connect(lambda: self._set_mode("toggle"))
        mode_menu.addAction(toggle_action)

        self._menu.addSeparator()
        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.signals.open_settings.emit)
        self._menu.addAction(settings_action)

        test_action = QAction("Test Microphone")
        test_action.triggered.connect(self.signals.test_microphone.emit)
        self._menu.addAction(test_action)

        self._menu.addSeparator()
        exit_action = QAction("Exit")
        exit_action.triggered.connect(self.signals.exit_app.emit)
        self._menu.addAction(exit_action)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._build_menu()
        self.signals.mode_changed.emit(mode)

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        self._build_menu()
        if self._tray is not None:
            if recording:
                self._tray.setToolTip("VoiceType - Recording...")
            else:
                self._tray.setToolTip("VoiceType - Ready")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.signals.start_recording.emit()

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()
```

- [ ] **Step 2: Run smoke test**

Run: `cd D:\dev\TT && python -c "from voice_typing.ui.tray import TrayIcon; print('OK')"`
Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
git add voice_typing/ui/tray.py
git commit -m "feat: system tray icon with context menu"
```

---

### Task 8: Floating Status Bar

**Files:**
- Create: `voice_typing/ui/status_bar.py`

**Interfaces:**
- Produces: `StatusBar` class — `show()`, `hide()`, `set_state(state, text)`

- [ ] **Step 1: Implement StatusBar**

```python
# voice_typing/ui/status_bar.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget


class StatusBar:
    def __init__(self) -> None:
        self._window: QWidget | None = None
        self._label: QLabel | None = None

    def show(self) -> None:
        if self._window is not None:
            self._window.show()
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self._window = QWidget()
        self._window.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        width = 350
        height = 60
        x = (geo.width() - width) // 2 + geo.x()
        y = geo.height() - height - 40 + geo.y()
        self._window.setGeometry(x, y, width, height)
        self._label = QLabel("🟢 Ready", self._window)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "background-color: rgba(30, 30, 30, 220); "
            "color: white; "
            "font-size: 14px; "
            "padding: 8px; "
            "border-radius: 8px;"
        )
        self._window.setStyleSheet("background: transparent;")
        self._window.show()

    def set_state(self, state: str, text: str = "") -> None:
        if self._label is None:
            return
        icons = {"ready": "🟢", "listening": "🔴", "processing": "⚡"}
        icon = icons.get(state, "⚪")
        display = f"{icon} {text}" if text else f"{icon} {state.title()}..."
        self._label.setText(display)

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def close(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None
            self._label = None
```

- [ ] **Step 2: Commit**

```bash
git add voice_typing/ui/status_bar.py
git commit -m "feat: floating status bar (frameless, no focus steal)"
```

---

### Task 9: Settings Window

**Files:**
- Create: `voice_typing/ui/settings_window.py`

**Interfaces:**
- Consumes: `SettingsManager` from Task 1
- Produces: `SettingsWindow` class — `show()`, `close()`, `saved` signal

- [ ] **Step 1: Implement SettingsWindow**

```python
# voice_typing/ui/settings_window.py
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.config.settings import SettingsManager


class SettingsWindow(QDialog):
    saved = Signal()

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("VoiceType Settings")
        self.setMinimumSize(550, 450)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._hotkey_tab(), "Hotkey")
        tabs.addTab(self._speech_tab(), "Speech")
        tabs.addTab(self._gemini_tab(), "Gemini")
        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_and_close)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _general_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        self._start_windows = QCheckBox()
        self._start_windows.setChecked(self._settings.get("start_with_windows", False))
        layout.addRow("Start with Windows:", self._start_windows)

        self._show_status = QCheckBox()
        self._show_status.setChecked(self._settings.get("show_status_bar", True))
        layout.addRow("Show status bar:", self._show_status)

        self._sound_feedback = QCheckBox()
        self._sound_feedback.setChecked(self._settings.get("sound_feedback", True))
        layout.addRow("Sound feedback:", self._sound_feedback)
        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        self._hotkey_input = QLineEdit(hex(self._settings.get("hotkey", 0x7E)))
        layout.addRow("Push-to-Talk key:", self._hotkey_input)
        return w

    def _speech_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Auto", "Thai", "English"])
        current = self._settings.get("language", "auto")
        idx = {"auto": 0, "thai": 1, "english": 2}.get(current, 0)
        self._lang_combo.setCurrentIndex(idx)
        layout.addRow("Language:", self._lang_combo)

        self._mic_list = QListWidget()
        layout.addRow("Microphone:", self._mic_list)
        return w

    def _gemini_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setText(self._settings.get("api_key", ""))
        layout.addRow("API Key:", self._api_key)

        self._fast_mode = QCheckBox()
        self._fast_mode.setChecked(self._settings.get("fast_mode", True))
        layout.addRow("Fast Mode (skip AI processing):", self._fast_mode)
        return w

    def _save_and_close(self) -> None:
        self._settings.set("start_with_windows", self._start_windows.isChecked())
        self._settings.set("show_status_bar", self._show_status.isChecked())
        self._settings.set("sound_feedback", self._sound_feedback.isChecked())
        lang_map = {0: "auto", 1: "thai", 2: "english"}
        self._settings.set("language", lang_map.get(self._lang_combo.currentIndex(), "auto"))
        self._settings.set("api_key", self._api_key.text())
        self._settings.set("fast_mode", self._fast_mode.isChecked())
        try:
            self._settings.set("hotkey", int(self._hotkey_input.text(), 0))
        except ValueError:
            pass
        self._settings.save()
        self.saved.emit()
        self.close()
```

- [ ] **Step 2: Commit**

```bash
git add voice_typing/ui/settings_window.py
git commit -m "feat: tabbed settings window"
```

---

### Task 10: AI Text Processor (Smart Mode)

**Files:**
- Create: `voice_typing/ai/__init__.py`
- Create: `voice_typing/ai/text_processor.py`

**Interfaces:**
- Produces: `TextProcessor` class — `async process(text: str) -> str`

- [ ] **Step 1: Implement TextProcessor**

```python
# voice_typing/ai/text_processor.py
from __future__ import annotations

import aiohttp


class TextProcessor:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._api_key = api_key
        self._model = model

    async def process(self, text: str) -> str:
        if not text.strip():
            return text
        prompt = (
            "Fix punctuation and formatting in this transcription. "
            "Support both Thai and English. Keep the original meaning. "
            "Output only the corrected text.\n\n"
            f"Transcription: {text}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            return "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            pass
        return text
```

- [ ] **Step 2: Commit**

```bash
git add voice_typing/ai/
git commit -m "feat: AI text processor for Smart Mode"
```

---

### Task 11: App Entry Point — Wiring Everything Together

**Files:**
- Create: `voice_typing/app.py`

**Interfaces:**
- Consumes: All previous components

- [ ] **Step 1: Implement app.py**

```python
# voice_typing/app.py
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import QApplication

from voice_typing.ai.text_processor import TextProcessor
from voice_typing.audio.recorder import AudioRecorder
from voice_typing.config.settings import SettingsManager
from voice_typing.speech.engine import TranscriptBuffer
from voice_typing.speech.gemini_live import GeminiLiveClient
from voice_typing.ui.settings_window import SettingsWindow
from voice_typing.ui.status_bar import StatusBar
from voice_typing.ui.tray import TrayIcon
from voice_typing.windows.hotkey import HotkeyManager
from voice_typing.windows.text_injector import TextInjector


class WorkerSignals(QObject):
    partial_received = Signal(str)
    final_received = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    error = Signal(str)


class WorkerThread(QThread):
    def __init__(self, settings: SettingsManager) -> None:
        super().__init__()
        self._settings = settings
        self._signals = WorkerSignals()
        self._recorder = AudioRecorder()
        self._buffer = TranscriptBuffer()
        self._injector = TextInjector()
        self._hotkey_mgr = HotkeyManager()
        self._client: GeminiLiveClient | None = None
        self._processor: TextProcessor | None = None
        self._is_toggle_mode = False
        self._recording = False

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        if self._client is not None and self._client.is_connected:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._client.send_audio(audio_bytes))
            loop.close()

    def _on_hotkey(self, vk_code: int) -> None:
        if self._is_toggle_mode:
            if self._recording:
                self._finalize_and_inject()
            else:
                self._start_recording()
        else:
            if self._recording:
                self._finalize_and_inject()

    def _start_recording(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._signals.recording_started.emit()
        self._recorder.start(callback=self._on_audio_chunk)

    def _finalize_and_inject(self) -> None:
        self._recorder.stop()
        self._recording = False
        self._signals.recording_stopped.emit()
        text = self._buffer.finalize()
        if text.strip():
            self._injector.inject(text)

    def _on_partial(self, text: str) -> None:
        self._buffer.add_partial(text)
        self._signals.partial_received.emit(text)

    def _on_final(self, text: str) -> None:
        self._buffer.add_partial(text)
        self._finalize_and_inject()

    def run(self) -> None:
        api_key = self._settings.get("api_key", "")
        if not api_key:
            self._signals.error.emit("No API key configured")
            return

        self._client = GeminiLiveClient(api_key=api_key)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._client.connect())

        self._hotkey_mgr.register(
            self._settings.get("hotkey", 0x7E), self._on_hotkey
        )
        self._hotkey_mgr.start()

        while self._client.is_connected:
            loop.run_until_complete(
                self._client.receive_transcript(
                    on_partial=self._on_partial, on_final=self._on_final
                )
            )

        loop.run_until_complete(self._client.disconnect())
        self._hotkey_mgr.stop()


class VoiceTypeApp:
    def __init__(self) -> None:
        self._qapp = QApplication(sys.argv)
        self._qapp.setQuitOnLastWindowClosed(False)
        config_dir = Path.home() / "AppData" / "Roaming" / "VoiceType"
        self._settings = SettingsManager(config_dir / "settings.json")
        self._settings.load()
        self._tray = TrayIcon()
        self._status_bar = StatusBar()
        self._settings_win: SettingsWindow | None = None
        self._worker: WorkerThread | None = None

    def run(self) -> int:
        self._tray.signals.start_recording.connect(self._start_recording)
        self._tray.signals.stop_recording.connect(self._stop_recording)
        self._tray.signals.open_settings.connect(self._open_settings)
        self._tray.signals.exit_app.connect(self._exit)
        self._tray.signals.mode_changed.connect(self._on_mode_changed)
        self._tray.show()
        return self._qapp.exec()

    def _start_recording(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = WorkerThread(self._settings)
        self._worker._signals.recording_started.connect(self._on_recording_started)
        self._worker._signals.recording_stopped.connect(self._on_recording_stopped)
        self._worker._signals.partial_received.connect(self._on_partial)
        self._worker._signals.error.connect(self._on_error)
        self._worker.start()

    def _stop_recording(self) -> None:
        if self._worker is not None:
            self._worker._finalize_and_inject()

    def _on_recording_started(self) -> None:
        self._tray.update_recording_state(True)
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
            self._status_bar.set_state("listening", "Listening...")

    def _on_recording_stopped(self) -> None:
        self._tray.update_recording_state(False)
        self._status_bar.set_state("ready")
        self._status_bar.hide()

    def _on_partial(self, text: str) -> None:
        self._status_bar.set_state("listening", text)

    def _on_error(self, msg: str) -> None:
        self._status_bar.set_state("error", msg)

    def _on_mode_changed(self, mode: str) -> None:
        self._settings.set("mode", mode)
        self._settings.save()

    def _open_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self._settings)
        self._settings_win.show()

    def _exit(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker._finalize_and_inject()
            self._worker.quit()
            self._worker.wait(2000)
        self._status_bar.close()
        self._tray.hide()
        self._qapp.quit()


def main() -> int:
    app = VoiceTypeApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit**

```bash
git add voice_typing/app.py
git commit -m "feat: app entry point with full wiring"
```

---

### Task 12: Integration Test + Smoke Test

**Files:**
- Create: `tests/test_app.py`

**Interfaces:**
- Consumes: All components

- [ ] **Step 1: Write smoke test**

```python
# tests/test_app.py
def test_imports():
    from voice_typing.config.settings import SettingsManager
    from voice_typing.audio.recorder import AudioRecorder
    from voice_typing.speech.engine import TranscriptBuffer
    from voice_typing.windows.text_injector import TextInjector
    from voice_typing.windows.hotkey import HotkeyManager
    from voice_typing.speech.gemini_live import GeminiLiveClient
    assert True


def test_full_flow_mock():
    from voice_typing.config.settings import SettingsManager
    from voice_typing.speech.engine import TranscriptBuffer
    from voice_typing.windows.text_injector import TextInjector
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "settings.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        mgr.save()

        buf = TranscriptBuffer()
        buf.add_partial("hello")
        buf.add_partial("hello world")
        result = buf.finalize()
        assert result == "hello world"
```

- [ ] **Step 2: Run all tests**

Run: `cd D:\dev\TT && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_app.py
git commit -m "feat: integration smoke tests"
```

---

### Task 13: First-Run Wizard

**Files:**
- Modify: `voice_typing/app.py` (add wizard trigger)

**Interfaces:**
- Consumes: `SettingsManager` from Task 1

- [ ] **Step 1: Create setup wizard**

Add `_run_setup_wizard()` method to `VoiceTypeApp` in `voice_typing/app.py`:

```python
# Add this method to the VoiceTypeApp class in voice_typing/app.py:
from PySide6.QtWidgets import QInputDialog, QMessageBox

def _run_setup_wizard(self) -> None:
    if self._settings.get("api_key"):
        return
    api_key, ok = QInputDialog.getText(
        None, "VoiceType Setup", "Enter your Gemini API Key:"
    )
    if ok and api_key.strip():
        self._settings.set("api_key", api_key.strip())
        self._settings.save()
    else:
        QMessageBox.warning(
            None,
            "VoiceType Setup",
            "No API key entered. You can configure it later in Settings.",
        )
```

- [ ] **Step 2: Call wizard from run()**

In `VoiceTypeApp.run()`, add `self._run_setup_wizard()` before `self._tray.show()`.

- [ ] **Step 3: Commit**

```bash
git add voice_typing/app.py
git commit -m "feat: first-run setup wizard for API key"
```

---

### Task 14: PyInstaller Build Config

**Files:**
- Create: `build.spec`

- [ ] **Step 1: Create build.spec**

```python
# build.spec
a = Analysis(
    ["voice_typing/app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        "sounddevice",
        "numpy",
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceType",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
```

- [ ] **Step 2: Commit**

```bash
git add build.spec
git commit -m "feat: PyInstaller build spec"
```
