# voice_typing/ui/settings_window.py
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

from PySide6.QtCore import QEvent, QObject, Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.audio.recorder import list_input_devices
from voice_typing.config.settings import DEFAULT_SETTINGS, SettingsManager, VERSION, RELEASE_URL, get_asset_path
from voice_typing.speech.gemini_live import MODEL, fetch_live_models
from voice_typing.windows.hotkey import HOTKEY_OPTIONS, hotkey_name


def _normalize_model(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return MODEL
    return name if name.startswith("models/") else f"models/{name}"


class _ModelLoader(QThread):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    def run(self) -> None:
        try:
            self.finished.emit(fetch_live_models(self._api_key))
        except Exception as exc:
            self.failed.emit(str(exc))


class _ApiKeyTester(QThread):
    finished = Signal(bool, str)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    def run(self) -> None:
        try:
            models = fetch_live_models(self._api_key)
            if models:
                self.finished.emit(True, f"API Key is valid! Connected to Gemini API ({len(models)} models available).")
            else:
                self.finished.emit(False, "API Key test returned no models.")
        except Exception as exc:
            self.finished.emit(False, f"API Key test failed:\n{exc}")


class _LiveMicTester(QThread):
    level_changed = Signal(int)
    finished_test = Signal(bool, str)

    def __init__(self, device_id: int | None = None, duration_sec: float = 5.0) -> None:
        super().__init__()
        self._device_id = device_id
        self._duration_sec = duration_sec
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        import time
        import numpy as np
        import sounddevice as sd

        self._running = True
        sample_rate = 16000
        blocksize = 1600

        def callback(indata, frames, time_info, status):
            if not self._running:
                return
            if indata.dtype == np.int16:
                samples = indata.astype(np.float32) / 32768.0
            else:
                samples = indata.astype(np.float32)
            peak = float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0
            level = int(min(100, max(0, peak * 100)))
            self.level_changed.emit(level)

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                device=self._device_id,
                callback=callback,
            ):
                start_time = time.time()
                while self._running and (time.time() - start_time < self._duration_sec):
                    time.sleep(0.05)
        except Exception as exc:
            log.warning("Mic test failed: %s", exc)
            self.finished_test.emit(False, f"Mic test failed: {exc}")
        finally:
            self._running = False


class SettingsWindow(QDialog):
    saved = Signal()

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._key_tester: _ApiKeyTester | None = None
        self._model_loader: _ModelLoader | None = None
        self._mic_tester: _LiveMicTester | None = None
        self._capturing_key = False
        self._capture_timer: QTimer | None = None
        self.setWindowTitle("VoiceType Settings")
        icon_path = get_asset_path("icon.ico")
        if not icon_path.exists():
            icon_path = get_asset_path("icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(420, 380)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #1a1b1e; color: #e8eaed; font-family: 'Segoe UI', sans-serif; }
            QTabWidget::pane { border: none; background: #1a1b1e; }
            QTabBar { background: transparent; }
            QTabBar::tab { background: transparent; color: #9aa0a6; padding: 8px 16px; border: none; border-bottom: 2px solid transparent; font-size: 11px; }
            QTabBar::tab:selected { color: #e8eaed; border-bottom: 2px solid #8ab4f8; }
            QTabBar::tab:hover { color: #c4c7c5; }
            QLabel { color: #9aa0a6; font-size: 11px; background: transparent; border: none; }
            QLineEdit { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 10px; font-size: 11px; selection-background-color: #264f78; }
            QLineEdit:focus { border-color: #8ab4f8; }
            QComboBox { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 10px; font-size: 11px; min-height: 20px; }
            QComboBox:hover { border-color: #5f6368; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #9aa0a6; margin-right: 8px; }
            QComboBox QAbstractItemView { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; selection-background-color: #303134; }
            QComboBox:disabled { background: #2b2d31; color: #5f6368; border: 1px solid #3c4043; }
            QCheckBox { color: #e8eaed; spacing: 8px; font-size: 11px; background: transparent; border: none; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid #5f6368; background: transparent; }
            QCheckBox::indicator:hover { border-color: #8ab4f8; }
            QCheckBox::indicator:checked { background: #8ab4f8; border-color: #8ab4f8; }
            QCheckBox::indicator:checked:hover { background: #aecbfa; border-color: #aecbfa; }
            QCheckBox:disabled { color: #5f6368; }
            QCheckBox:disabled::indicator { border-color: #3c4043; }
            QSlider::groove:horizontal { background: #3c4043; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #8ab4f8; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: #aecbfa; }
            QSlider::sub-page:horizontal { background: #8ab4f8; border-radius: 2px; }
            QPushButton { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; font-size: 11px; min-height: 20px; }
            QPushButton:hover { background: #383a40; border-color: #5f6368; }
            QPushButton:pressed { background: #4e525a; }
            QPushButton:disabled { background: #2b2d31; color: #5f6368; border: 1px solid #3c4043; }
            QPushButton#primaryBtn { background: #8ab4f8; color: #1a1b1e; border: none; font-weight: bold; }
            QPushButton#primaryBtn:hover { background: #aecbfa; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #3c4043; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #5f6368; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QMessageBox { background: #1a1b1e; }
            QMessageBox QLabel { color: #e8eaed; }
            QMessageBox QPushButton { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; }
            QMessageBox QPushButton:hover { background: #383a40; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "⚙️  General")
        tabs.addTab(self._hotkey_tab(), "⌨️  Hotkey")
        tabs.addTab(self._speech_tab(), "🎤  Speech")
        tabs.addTab(self._gemini_tab(), "🤖  AI / Gemini")
        tabs.addTab(self._about_tab(), "ℹ️  About")
        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #9aa0a6; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; font-size: 11px; }
            QPushButton:hover { background: #383a40; border-color: #5f6368; }
        """)
        cancel_btn.clicked.connect(self.close)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.setStyleSheet("""
            QPushButton { background: #8ab4f8; color: #1a1b1e; border: none; border-radius: 6px; padding: 6px 20px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background: #aecbfa; }
        """)
        save_btn.clicked.connect(self._save_and_close)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._populate_ui_from_settings()

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3c4043;")
        return sep

    def _general_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Push-to-Talk (hold key to record)", "push_to_talk")
        self._mode_combo.addItem("Toggle (press once to start/stop)", "toggle")
        layout.addRow("Recording Mode:", self._mode_combo)

        self._capsule_style_combo = QComboBox()
        self._capsule_style_combo.addItem("Dynamic Pill (always visible oval)", "pill")
        self._capsule_style_combo.addItem("Ultra-Minimal Dot (expands on speech/hover)", "dot")
        layout.addRow("Capsule Style:", self._capsule_style_combo)

        opacity_layout = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_label = QLabel()
        self._opacity_slider.valueChanged.connect(lambda v: self._opacity_label.setText(f"{v}%"))
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        layout.addRow("Capsule Opacity:", opacity_layout)

        self._start_windows = QCheckBox()
        layout.addRow("Start with Windows:", self._start_windows)

        self._show_status = QCheckBox()
        layout.addRow("Show floating status bar:", self._show_status)

        sound_layout = QHBoxLayout()
        self._sound_feedback = QCheckBox()
        self._test_sound_btn = QPushButton("🔊 Test Beep")
        self._test_sound_btn.clicked.connect(self._play_test_beep)
        sound_layout.addWidget(self._sound_feedback)
        sound_layout.addWidget(self._test_sound_btn)
        sound_layout.addStretch()
        layout.addRow("Sound feedback (beeps):", sound_layout)

        self._copy_to_clipboard = QCheckBox("Also copy recognized text to clipboard")
        layout.addRow("Clipboard:", self._copy_to_clipboard)

        # -- Transcript Overlay section ------------------------------------------
        layout.addRow("", self._make_separator())
        overlay_title = QLabel("Transcript Overlay")
        overlay_title.setStyleSheet(
            "color: #e8eaed; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addRow("", overlay_title)

        self._overlay_enabled = QCheckBox("Show live transcript overlay")
        layout.addRow("", self._overlay_enabled)

        overlay_opacity_layout = QHBoxLayout()
        self._overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._overlay_opacity_slider.setRange(50, 100)
        self._overlay_opacity_label = QLabel()
        self._overlay_opacity_slider.valueChanged.connect(
            lambda v: self._overlay_opacity_label.setText(f"{v}%")
        )
        overlay_opacity_layout.addWidget(self._overlay_opacity_slider)
        overlay_opacity_layout.addWidget(self._overlay_opacity_label)
        layout.addRow("Overlay Opacity:", overlay_opacity_layout)

        self._overlay_font_combo = QComboBox()
        self._overlay_font_combo.addItem("Small (11px)", 11)
        self._overlay_font_combo.addItem("Medium (13px)", 13)
        self._overlay_font_combo.addItem("Large (16px)", 16)
        layout.addRow("Overlay Font Size:", self._overlay_font_combo)

        overlay_dismiss_layout = QHBoxLayout()
        self._overlay_dismiss_slider = QSlider(Qt.Orientation.Horizontal)
        self._overlay_dismiss_slider.setRange(1, 10)
        self._overlay_dismiss_slider.setSingleStep(1)
        self._overlay_dismiss_label = QLabel()
        self._overlay_dismiss_slider.valueChanged.connect(
            lambda v: self._overlay_dismiss_label.setText(
                f"{v} {'sec' if v == 1 else 'secs'}"
            )
        )
        overlay_dismiss_layout.addWidget(self._overlay_dismiss_slider)
        overlay_dismiss_layout.addWidget(self._overlay_dismiss_label)
        layout.addRow("Auto-Dismiss Delay:", overlay_dismiss_layout)

        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._hotkey_combo = QComboBox()
        layout.addRow("Voice Typing Key / Button:", self._hotkey_combo)

        self._capture_btn = QPushButton("🎮  Press a key or mouse button to capture")
        self._capture_btn.clicked.connect(self._start_key_capture)
        layout.addRow("", self._capture_btn)

        hint = QLabel(
            "Push-to-Talk: hold the key/mouse button to record, release to type.\n"
            "Toggle: press once to start, press again to stop."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")

        keys_hint = QLabel(
            "Supported keys: F6-F12, CapsLock, and mouse side buttons / middle click."
        )
        keys_hint.setWordWrap(True)
        keys_hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        layout.addRow("", hint)
        layout.addRow("", keys_hint)

        return w

    def _speech_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Auto (Thai + English)", "Thai (ภาษาไทย)", "English"])
        layout.addRow("Language:", self._lang_combo)

        mic_layout = QHBoxLayout()
        self._mic_combo = QComboBox()
        refresh_btn = QPushButton("↺")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self._refresh_mics)
        mic_layout.addWidget(self._mic_combo, 1)
        mic_layout.addWidget(refresh_btn)
        layout.addRow("Microphone:", mic_layout)

        mic_level_layout = QHBoxLayout()
        self._mic_level_bar = QProgressBar()
        self._mic_level_bar.setRange(0, 100)
        self._mic_level_bar.setValue(0)
        self._mic_level_bar.setTextVisible(True)
        self._test_mic_btn = QPushButton("🎤 Test Mic")
        self._test_mic_btn.clicked.connect(self._toggle_mic_test)
        mic_level_layout.addWidget(self._mic_level_bar, 1)
        mic_level_layout.addWidget(self._test_mic_btn)
        layout.addRow("Audio Level:", mic_level_layout)

        speed_layout = QHBoxLayout()
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(0, 5)
        self._speed_slider.setSingleStep(1)
        self._speed_label = QLabel()
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText("Instant" if v == 0 else f"{v} ms/char")
        )
        speed_layout.addWidget(self._speed_slider)
        speed_layout.addWidget(self._speed_label)
        layout.addRow("Typing Speed:", speed_layout)

        sensitivity_layout = QHBoxLayout()
        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self._sensitivity_slider.setRange(1, 20)
        self._sensitivity_slider.setSingleStep(1)
        self._sensitivity_label = QLabel()
        self._sensitivity_slider.valueChanged.connect(self._update_sensitivity_label)
        sensitivity_layout.addWidget(self._sensitivity_slider)
        sensitivity_layout.addWidget(self._sensitivity_label)
        layout.addRow("Voice Sensitivity:", sensitivity_layout)

        return w

    def _update_sensitivity_label(self, v: int) -> None:
        if v <= 5:
            text = "Low"
        elif v <= 13:
            text = "Medium"
        else:
            text = "High"
        self._sensitivity_label.setText(text)

    def _gemini_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_status = QLabel("● Not tested")
        self._api_status.setObjectName("api_status")
        self._api_status.setStyleSheet("color: #9aa0a6; font-size: 16px;")
        
        self._test_key_btn = QPushButton("Test Key")
        self._test_key_btn.clicked.connect(self._test_api_key)

        key_layout = QHBoxLayout()
        key_layout.addWidget(self._api_key, 1)
        key_layout.addWidget(self._api_status)
        key_layout.addWidget(self._test_key_btn)
        layout.addRow("API Key:", key_layout)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(False)
        self._load_models_btn = QPushButton("Load models")
        self._load_models_btn.clicked.connect(self._load_models)

        model_layout = QHBoxLayout()
        model_layout.addWidget(self._model_combo, 1)
        model_layout.addWidget(self._load_models_btn)
        layout.addRow("Model:", model_layout)

        self._fast_mode = QCheckBox()
        layout.addRow("Fast Mode:", self._fast_mode)

        hint = QLabel("Skip AI punctuation correction for faster real-time response.")
        hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        self._custom_vocab = QLineEdit()
        self._custom_vocab.setPlaceholderText("e.g., Python, PySide6, Gemini, Prompt engineering")
        layout.addRow("Custom Vocabulary / Keywords:", self._custom_vocab)

        vocab_help = QLabel(
            "Add specific words, names, or jargon to help Gemini recognize them accurately."
        )
        vocab_help.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        vocab_help.setWordWrap(True)
        layout.addRow("", vocab_help)

        vocab_warning = QLabel(
            "\u26a0 Note: Requires \"Fast Mode\" to be OFF to take effect."
        )
        vocab_warning.setStyleSheet("color: #fbbc04; font-size: 10px;")
        vocab_warning.setWordWrap(True)
        layout.addRow("", vocab_warning)

        return w

    def _about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_label = QLabel()
        icon_path = get_asset_path("icon.png")
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(
                80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignCenter)

        title = QLabel("VoiceType")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e8eaed; margin-top: 8px;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f'<a href="{RELEASE_URL}" style="color: #8ab4f8; font-size: 12px; text-decoration: none;">v{VERSION}</a>')
        version.setOpenExternalLinks(True)
        version.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Real-time Thai + English voice-to-text for Windows")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #9aa0a6; margin-top: 8px; font-size: 12px;")
        layout.addWidget(desc, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        get_key_btn = QPushButton("🔑  Get Gemini API Key")
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8ab4f8; border: none; font-size: 12px; text-decoration: underline;
            }
            QPushButton:hover {
                color: #aecbfa;
            }
        """)
        get_key_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/apikey")))
        layout.addWidget(get_key_btn, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3c4043;")
        layout.addWidget(sep)

        reset_btn = QPushButton("⚠️  Reset All Settings to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #2b1a1a; color: #ea4335; border: 1px solid #ea4335; border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: 500;
            }
            QPushButton:hover { background: #3d1a1a; }
        """)
        reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(reset_btn, 0, Qt.AlignmentFlag.AlignCenter)

        return w

    def _play_test_beep(self) -> None:
        def _beep():
            try:
                import winsound
                winsound.Beep(1000, 150)
            except Exception:
                pass

        import threading
        threading.Thread(target=_beep, daemon=True).start()

    def _toggle_mic_test(self) -> None:
        if self._mic_tester is not None and self._mic_tester.isRunning():
            self._stop_mic_test()
        else:
            self._start_mic_test()

    def _start_mic_test(self) -> None:
        device_id = self._mic_combo.currentData()
        self._test_mic_btn.setText("⏹ Stop Test")
        self._mic_tester = _LiveMicTester(device_id=device_id)
        self._mic_tester.level_changed.connect(self._mic_level_bar.setValue)
        self._mic_tester.finished.connect(self._on_mic_test_finished)
        self._mic_tester.finished_test.connect(self._on_mic_test_finished)
        self._mic_tester.start()

    def _stop_mic_test(self) -> None:
        if self._mic_tester is not None:
            self._mic_tester.stop()
            self._mic_tester.wait(500)
        self._on_mic_test_finished()

    def _on_mic_test_finished(self, success: bool = True, msg: str = "") -> None:
        self._test_mic_btn.setText("🎤 Test Mic")
        self._mic_level_bar.setValue(0)
        if not success and msg:
            QMessageBox.warning(self, "Mic Test Error", msg)
        self._mic_tester = None

    def closeEvent(self, event) -> None:
        if self._capturing_key:
            self._cancel_key_capture()
        if self._mic_tester is not None and self._mic_tester.isRunning():
            self._mic_tester.stop()
            self._mic_tester.wait(300)
        super().closeEvent(event)

    def _populate_ui_from_settings(self) -> None:
        # General
        mode = self._settings.get("mode", "push_to_talk")
        self._mode_combo.setCurrentIndex(0 if mode == "push_to_talk" else 1)

        style = self._capsule_style_combo.findData(self._settings.get("capsule_style", "pill"))
        self._capsule_style_combo.setCurrentIndex(max(0, style))

        opacity_val = int(self._settings.get("opacity", 0.94) * 100)
        self._opacity_slider.setValue(opacity_val)
        self._opacity_label.setText(f"{self._opacity_slider.value()}%")

        self._start_windows.setChecked(self._settings.get("start_with_windows", False))
        self._show_status.setChecked(self._settings.get("show_status_bar", True))
        self._sound_feedback.setChecked(self._settings.get("sound_feedback", True))
        self._copy_to_clipboard.setChecked(self._settings.get("copy_to_clipboard", False))

        # Overlay
        self._overlay_enabled.setChecked(self._settings.get("overlay_enabled", True))
        overlay_opacity_val = int(self._settings.get("overlay_opacity", 0.92) * 100)
        self._overlay_opacity_slider.setValue(overlay_opacity_val)
        self._overlay_opacity_label.setText(f"{self._overlay_opacity_slider.value()}%")

        overlay_font = self._settings.get("overlay_font_size", 13)
        font_idx = self._overlay_font_combo.findData(overlay_font)
        if font_idx >= 0:
            self._overlay_font_combo.setCurrentIndex(font_idx)
        else:
            self._overlay_font_combo.setCurrentIndex(1)  # Default to Medium

        dismiss_val = int(self._settings.get("overlay_auto_dismiss_seconds", 3))
        self._overlay_dismiss_slider.setValue(dismiss_val)
        self._overlay_dismiss_label.setText(
            f"{dismiss_val} {'sec' if dismiss_val == 1 else 'secs'}"
        )

        # Hotkey
        current_hotkey = self._settings.get("hotkey", 0x78)
        self._hotkey_combo.clear()
        selected = 0
        for i, (name, code) in enumerate(HOTKEY_OPTIONS):
            self._hotkey_combo.addItem(name, code)
            if code == current_hotkey:
                selected = i
        if self._hotkey_combo.itemData(selected) != current_hotkey:
            self._hotkey_combo.addItem(hotkey_name(current_hotkey), current_hotkey)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)

        # Speech
        current_lang = self._settings.get("language", "auto")
        from voice_typing.config.settings import LANGUAGE_INDEX
        idx = LANGUAGE_INDEX.get(current_lang, 0)
        self._lang_combo.setCurrentIndex(idx)

        self._refresh_mics()
        current_mic = self._settings.get("microphone_device_id")
        mic_selected = 0
        for i in range(self._mic_combo.count()):
            if self._mic_combo.itemData(i) == current_mic:
                mic_selected = i
                break
        self._mic_combo.setCurrentIndex(mic_selected)

        speed_val = self._settings.get("typing_speed", 0)
        self._speed_slider.setValue(speed_val)
        v_spd = self._speed_slider.value()
        self._speed_label.setText("Instant" if v_spd == 0 else f"{v_spd} ms/char")

        sens_val = int(self._settings.get("silence_threshold", 0.005) * 1000)
        self._sensitivity_slider.setValue(sens_val)
        self._update_sensitivity_label(self._sensitivity_slider.value())

        # Gemini
        self._api_key.setText(self._settings.get("api_key", ""))
        self._api_status.setText("\u25cf Not tested")
        self._api_status.setStyleSheet("color: #9aa0a6; font-size: 16px;")

        current_model = _normalize_model(self._settings.get("model", MODEL))
        self._model_combo.clear()
        self._model_combo.addItem(current_model, current_model)
        self._model_combo.setCurrentIndex(0)

        self._fast_mode.setChecked(self._settings.get("fast_mode", True))
        self._custom_vocab.setText(self._settings.get("custom_vocabulary", ""))

    def _refresh_mics(self) -> None:
        current = self._mic_combo.currentData()
        self._mic_combo.clear()
        self._mic_combo.addItem("Default Microphone", None)
        try:
            for index, name in list_input_devices():
                self._mic_combo.addItem(name, index)
        except Exception:
            pass

        selected = 0
        if current is not None:
            for i in range(self._mic_combo.count()):
                if self._mic_combo.itemData(i) == current:
                    selected = i
                    break
        self._mic_combo.setCurrentIndex(selected)

    def _start_key_capture(self) -> None:
        self._capturing_key = True
        self._capture_btn.setText("⏳  Listening... (press key/mouse, Esc to cancel)")
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.installEventFilter(self)
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._cancel_key_capture)
        self._capture_timer.start(5000)

    def _cancel_key_capture(self) -> None:
        self._capturing_key = False
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.removeEventFilter(self)
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
            self._capture_timer = None
        self._capture_btn.setText("🎮  Press a key or mouse button to capture")

    def _apply_captured_vk(self, vk: int) -> None:
        selected = -1
        for i in range(self._hotkey_combo.count()):
            if self._hotkey_combo.itemData(i) == vk:
                selected = i
                break
        if selected == -1:
            name = hotkey_name(vk)
            self._hotkey_combo.addItem(name, vk)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)
        self._cancel_key_capture()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._capturing_key and event.type() == QEvent.Type.MouseButtonPress:
            btn = event.button()
            vk = 0
            if btn == Qt.MouseButton.MiddleButton:
                vk = 0x04
            elif btn in (Qt.MouseButton.BackButton, Qt.MouseButton.XButton1):
                vk = 0x05
            elif btn in (Qt.MouseButton.ForwardButton, Qt.MouseButton.XButton2):
                vk = 0x06
            if vk > 0:
                self._apply_captured_vk(vk)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self._capturing_key:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_key_capture()
                event.accept()
                return
            vk = event.nativeVirtualKey()
            if vk > 0:
                self._apply_captured_vk(vk)
                event.accept()
                return
        super().keyPressEvent(event)

    def _test_api_key(self) -> None:
        api_key = self._api_key.text().strip()
        if not api_key:
            QMessageBox.warning(self, "API Key Required", "Enter an API Key to test.")
            return
        self._test_key_btn.setEnabled(False)
        self._test_key_btn.setText("Testing...")
        self._api_status.setText("\u25cf Testing...")
        self._api_status.setStyleSheet("color: #fbbc04; font-size: 16px;")
        tester = _ApiKeyTester(api_key)
        tester.finished.connect(self._on_api_key_tested)
        tester.start()
        self._key_tester = tester

    def _on_api_key_tested(self, success: bool, msg: str) -> None:
        self._test_key_btn.setEnabled(True)
        self._test_key_btn.setText("Test Key")
        if success:
            self._api_status.setText("\u25cf Valid")
            self._api_status.setStyleSheet("color: #34a853; font-size: 16px;")
            QMessageBox.information(self, "API Key Test", msg)
        else:
            self._api_status.setText("\u25cf Invalid")
            self._api_status.setStyleSheet("color: #ea4335; font-size: 16px;")
            QMessageBox.warning(self, "API Key Test", msg)

    def _load_models(self) -> None:
        api_key = self._api_key.text().strip()
        if not api_key:
            QMessageBox.warning(
                self, "API Key Required", "Enter your Gemini API key first."
            )
            return
        self._load_models_btn.setEnabled(False)
        self._load_models_btn.setText("Loading...")
        loader = _ModelLoader(api_key)
        loader.finished.connect(self._on_models_loaded)
        loader.failed.connect(self._on_models_failed)
        loader.start()
        self._model_loader = loader

    def _on_models_loaded(self, models: list) -> None:
        self._load_models_btn.setEnabled(True)
        self._load_models_btn.setText("Load models")
        current = _normalize_model(self._settings.get("model", MODEL))
        self._model_combo.clear()
        selected = 0
        for i, name in enumerate(models):
            norm_name = _normalize_model(name)
            self._model_combo.addItem(norm_name, norm_name)
            if norm_name == current:
                selected = i
        if self._model_combo.count() == 0 or self._model_combo.itemData(selected) != current:
            self._model_combo.addItem(f"Custom: {current}", current)
            selected = self._model_combo.count() - 1
        self._model_combo.setCurrentIndex(selected)

    def _on_models_failed(self, reason: str) -> None:
        self._load_models_btn.setEnabled(True)
        self._load_models_btn.setText("Load models")
        QMessageBox.warning(
            self, "Load Models Failed", f"Could not fetch models:\n{reason[:400]}"
        )

    def _reset_to_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "Reset Settings", "This will reset all settings to defaults. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for k, v in DEFAULT_SETTINGS.items():
                self._settings.set(k, v)
            self._populate_ui_from_settings()
            QMessageBox.information(self, "Done", "Settings have been reset to defaults.")

    def _save_and_close(self) -> None:
        self._settings.set("mode", str(self._mode_combo.currentData()))
        self._settings.set("capsule_style", str(self._capsule_style_combo.currentData()))
        self._settings.set("opacity", self._opacity_slider.value() / 100.0)
        self._settings.set("start_with_windows", self._start_windows.isChecked())
        self._settings.set("show_status_bar", self._show_status.isChecked())
        self._settings.set("sound_feedback", self._sound_feedback.isChecked())
        self._settings.set("copy_to_clipboard", self._copy_to_clipboard.isChecked())
        lang_map = {0: "auto", 1: "thai", 2: "english"}
        self._settings.set("language", lang_map.get(self._lang_combo.currentIndex(), "auto"))
        self._settings.set("microphone_device_id", self._mic_combo.currentData())
        self._settings.set("typing_speed", self._speed_slider.value())
        self._settings.set("silence_threshold", self._sensitivity_slider.value() / 1000.0)
        self._settings.set("api_key", self._api_key.text().strip())
        model_data = self._model_combo.currentData()
        if model_data is None:
            model_data = self._model_combo.currentText()
        self._settings.set("model", _normalize_model(str(model_data)))
        self._settings.set("fast_mode", self._fast_mode.isChecked())
        self._settings.set("custom_vocabulary", self._custom_vocab.text().strip())
        hotkey_val = self._hotkey_combo.currentData()
        self._settings.set("hotkey", int(hotkey_val) if hotkey_val is not None else 0x78)
        # Overlay settings
        self._settings.set("overlay_enabled", self._overlay_enabled.isChecked())
        self._settings.set(
            "overlay_opacity", self._overlay_opacity_slider.value() / 100.0
        )
        font_data = self._overlay_font_combo.currentData()
        self._settings.set("overlay_font_size", int(font_data) if font_data else 13)
        self._settings.set(
            "overlay_auto_dismiss_seconds", self._overlay_dismiss_slider.value()
        )

        self._settings.save()
        self.saved.emit()
        self.close()