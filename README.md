# 🎙️ VoiceType — Real-time AI Voice Typing for Windows

<p align="center">
  <img src="voice_typing/assets/icon.png" alt="VoiceType Logo" width="120" height="120" />
</p>

<p align="center">
  <strong>Fast, accurate, and seamless real-time voice-to-text for Windows powered by Google Gemini Live WebSocket API.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-brightgreen.svg" alt="PySide6" />
  <img src="https://img.shields.io/badge/AI%20Model-Gemini%20Live%20API-orange.svg" alt="Gemini Live" />
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6.svg" alt="Windows" />
  <img src="https://img.shields.io/badge/Tests-112%20Passed-success.svg" alt="Tests" />
</p>

---

## ✨ Features

### ⚡ Real-Time Streaming Speech Recognition
* **Gemini Live WebSocket Engine**: Streams raw PCM audio in real-time with sub-second transcription response.
* **Fast Mode**: Instantly injects transcribed text with zero latency directly into any active application (Chrome, VS Code, Discord, Word, Line, Notion, etc.).

### 💊 Modern Dynamic Capsule Floating UI
* **Dynamic Pill Style**: An elegant floating capsule widget with a live animated audio visualizer.
* **Ultra-Minimal Dot Style**: A tiny discreet circle that expands automatically on hover or speech.
* **Customizable Opacity & Placement**: Draggable anywhere on the screen with position memory and adjustable transparency.

### 🎮 Keyboard & Mouse Button Triggers
* **Push-to-Talk Mode**: Hold the key or mouse button while speaking; text is automatically typed upon release.
* **Toggle Mode**: Click or press once to start listening, and press again to finish.
* **Supported Inputs**:
  * 🖱️ **Mouse Side Buttons (Back / Forward / XButton 1 & 2)**
  * 🖱️ **Mouse Middle Click (Scroll Wheel Click)**
  * ⌨️ **Keyboard Keys**: F1–F12, Caps Lock, Insert, Scroll Lock, Home, End, Letters, and Numbers.
  * 🎯 **One-Click Input Capture**: Detects and binds any key or mouse button in Settings.

### 🇹🇭 Strict Dual-Language Support (Thai & English)
* **Thai (ภาษาไทย)**: Strict Thai mode ensures pure Thai output without accidental English phonetic mixing.
* **English**: Strict English transcription.
* **Auto (Thai + English)**: Automatically detects and switches between Thai and English.
* **Quick Switcher**: Change languages instantly from the floating capsule menu (`⋯`), System Tray, or Settings.

### ⚙️ Rich Settings & Utility Suite
* **Custom Vocabulary**: Add domain-specific terms, technical keywords, or proper nouns to improve AI accuracy.
* **Live Mic Audio Level Meter**: Test and visualize input levels directly with the integrated `[🎤 Test Mic]` monitor.
* **Auto-Copy to Clipboard**: Optionally copy every transcribed utterance to the Windows clipboard simultaneously.
* **Typing Speed & Sensitivity Sliders**: Fine-tune character delivery intervals and silence thresholds.
* **System Tray & Windows Startup**: Full background tray integration with history recall and optional auto-start on boot.

---

## 🚀 Quick Start

### 1. Prerequisites
* **Windows 10 / 11** (64-bit)
* **Python 3.11+**
* A **Google Gemini API Key** (Free tier available at [Google AI Studio](https://aistudio.google.com/apikey))

### 2. Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Sirawit-Thong/VoiceType.git
   cd VoiceType
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```powershell
   pip install -e .
   ```

### 3. Run Application

```powershell
python -m voice_typing.app
```

On first launch, enter your **Gemini API Key** in the Setup Wizard or Settings window.

---

## 📦 Build Standalone Executable (.exe)

You can package VoiceType into a standalone Windows `.exe` using PyInstaller:

1. **Install PyInstaller:**
   ```powershell
   pip install pyinstaller
   ```

2. **Build with spec file:**
   ```powershell
   pyinstaller build.spec --clean --noconfirm
   ```

3. The generated executable will be located at:
   ```
   dist/VoiceType.exe
   ```

---

## 📁 Project Structure

```
VoiceType/
├── voice_typing/
│   ├── ai/                 # AI post-processing & text refinement
│   │   └── text_processor.py
│   ├── assets/             # App icons & graphic resources
│   │   ├── icon.ico
│   │   └── icon.png
│   ├── audio/              # Microphone capture & device enumeration
│   │   └── recorder.py
│   ├── config/             # Configuration management & asset resolver
│   │   └── settings.py
│   ├── speech/             # Gemini Live WebSocket client & audio streaming
│   │   ├── engine.py
│   │   └── gemini_live.py
│   ├── ui/                 # Modern PySide6 UI components
│   │   ├── settings_window.py # High-contrast Settings Dialog
│   │   ├── status_bar.py      # Floating Dynamic Capsule Bar
│   │   └── tray.py            # System Tray Icon & context menu
│   ├── windows/            # Windows OS interop (Hotkeys, Unicode injection, Startup)
│   │   ├── hotkey.py
│   │   ├── startup.py
│   │   └── text_injector.py
│   └── app.py              # Main application entry point & coordinator
├── tests/                  # 112+ Unit & Integration Tests (pytest)
├── build.spec              # PyInstaller build specification
├── pyproject.toml          # Project configuration & dependencies
└── README.md               # Project documentation
```

---

## 🧪 Testing

Run the automated test suite with `pytest`:

```powershell
pytest -v
```

All 112 tests covering audio buffers, text injection, hotkey handling, settings persistence, and UI components should pass.

## 📄 License & Terms of Use

Copyright © 2026 **Sirawit Thong (Sirawit-Thong)**. All rights reserved.

This project is licensed under the **Non-Commercial License (CC BY-NC 4.0 Compatible)**:
* ✅ **Allowed**: Free for personal, hobby, educational, research, and non-profit use. You are welcome to inspect, customize, fork, and modify the source code.
* ❌ **Prohibited**: Any commercial use, resale, paid distribution, or bundling into commercial products/services is strictly prohibited without explicit written permission.

See the full [LICENSE](LICENSE) file for complete terms and details.
