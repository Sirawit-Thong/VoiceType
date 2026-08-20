# voice_typing/ui/settings_window.py
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.audio.recorder import list_input_devices
from voice_typing.config.settings import DEFAULT_SETTINGS, SettingsManager
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


class SettingsWindow(QDialog):
    saved = Signal()

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._key_tester: _ApiKeyTester | None = None
        self._model_loader: _ModelLoader | None = None
        self._capturing_key = False
        self._capture_timer: QTimer | None = None
        self.setWindowTitle("VoiceType Settings")
        self.setMinimumSize(580, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #1e1f22; color: #e8eaed; }
            QTabWidget { background: transparent; }
            QTabWidget::pane { border: 1px solid #3c4043; border-radius: 6px; top: -1px; }
            QTabBar::tab { background: #2c2d30; color: #9aa0a6; padding: 8px 16px; border-radius: 6px 6px 0 0; }
            QTabBar::tab:selected { background: #1e1f22; color: #e8eaed; border-bottom: 2px solid #1a73e8; }
            QLabel { color: #e8eaed; }
            QComboBox { background: #2c2d30; color: #e8eaed; border: 1px solid #5f6368; border-radius: 4px; padding: 4px 8px; }
            QLineEdit { background: #2c2d30; color: #e8eaed; border: 1px solid #5f6368; border-radius: 4px; padding: 4px 8px; }
            QCheckBox { color: #e8eaed; }
            QPushButton { background: #2c2d30; color: #e8eaed; border: 1px solid #5f6368; border-radius: 6px; padding: 5px 14px; }
            QSlider::groove:horizontal { background: #3c4043; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #1a73e8; width: 14px; height: 14px; border-radius: 7px; margin: -5px 0; }
        """)

        layout = QVBoxLayout(self)
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
            QPushButton {
                background: transparent; border: 1px solid #5f6368; color: #bdc1c6;
                border-radius: 6px; padding: 6px 18px;
            }
            QPushButton:hover { background: #303134; }
        """)
        cancel_btn.clicked.connect(self.close)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #1a73e8; color: white; border: none;
                border-radius: 6px; padding: 6px 20px; font-weight: bold;
            }
            QPushButton:hover { background: #1557b0; }
        """)
        save_btn.clicked.connect(self._save_and_close)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._populate_ui_from_settings()

    def _general_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

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

        self._sound_feedback = QCheckBox()
        layout.addRow("Sound feedback (beeps):", self._sound_feedback)

        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        self._hotkey_combo = QComboBox()
        layout.addRow("Voice Typing Key:", self._hotkey_combo)

        self._capture_btn = QPushButton("🎹  Press a key to capture")
        self._capture_btn.clicked.connect(self._start_key_capture)
        layout.addRow("", self._capture_btn)

        hint = QLabel(
            "Push-to-Talk: hold the key to record, release to type. "
            "Toggle: press once to start, press again to stop. "
            "Switch modes from the tray icon menu (Mode)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a6;")
        layout.addRow("", hint)

        return w

    def _speech_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Auto (Thai + English)", "Thai (ภาษาไทย)", "English"])
        layout.addRow("Language:", self._lang_combo)

        mic_layout = QHBoxLayout()
        self._mic_combo = QComboBox()
        refresh_btn = QPushButton("↺")
        refresh_btn.setFixedWidth(32)
        refresh_btn.clicked.connect(self._refresh_mics)
        mic_layout.addWidget(self._mic_combo, 1)
        mic_layout.addWidget(refresh_btn)
        layout.addRow("Microphone:", mic_layout)

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

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_status = QLabel("●")
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
        hint.setStyleSheet("color: #9aa0a6; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        return w

    def _about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_label = QLabel()
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignCenter)

        title = QLabel("VoiceType")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #e8eaed; margin-top: 8px;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)

        version = QLabel("v1.0.0")
        version.setStyleSheet("color: #9aa0a6; font-size: 13px;")
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Real-time Thai + English voice-to-text for Windows")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #9aa0a6; margin-top: 8px;")
        layout.addWidget(desc, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        get_key_btn = QPushButton("🔑  Get Gemini API Key")
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #1a73e8; border: none; font-size: 13px; text-decoration: underline;
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
                background: #3d1a1a; color: #ea4335; border: 1px solid #ea4335; border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background: #5c2020; }
        """)
        reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(reset_btn, 0, Qt.AlignmentFlag.AlignCenter)

        return w

    def _populate_ui_from_settings(self) -> None:
        # General
        mode = self._settings.get("mode", "push_to_talk")
        self._mode_combo.setCurrentIndex(0 if mode == "push_to_talk" else 1)

        style = self._settings.get("capsule_style", "pill")
        self._capsule_style_combo.setCurrentIndex(0 if style == "pill" else 1)

        opacity_val = int(self._settings.get("opacity", 0.94) * 100)
        self._opacity_slider.setValue(opacity_val)
        self._opacity_label.setText(f"{self._opacity_slider.value()}%")

        self._start_windows.setChecked(self._settings.get("start_with_windows", False))
        self._show_status.setChecked(self._settings.get("show_status_bar", True))
        self._sound_feedback.setChecked(self._settings.get("sound_feedback", True))

        # Hotkey
        current_hotkey = self._settings.get("hotkey", 0x78)
        self._hotkey_combo.clear()
        selected = 0
        for i, (name, code) in enumerate(HOTKEY_OPTIONS):
            self._hotkey_combo.addItem(f"{name} ({hex(code)})", code)
            if code == current_hotkey:
                selected = i
        if self._hotkey_combo.itemData(selected) != current_hotkey:
            self._hotkey_combo.addItem(f"Custom ({hex(current_hotkey)})", current_hotkey)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)

        # Speech
        current_lang = self._settings.get("language", "auto")
        idx = {"auto": 0, "thai": 1, "english": 2}.get(current_lang, 0)
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
        self._api_status.setStyleSheet("color: #9aa0a6; font-size: 16px;")

        current_model = _normalize_model(self._settings.get("model", MODEL))
        self._model_combo.clear()
        self._model_combo.addItem(current_model, current_model)
        self._model_combo.setCurrentIndex(0)

        self._fast_mode.setChecked(self._settings.get("fast_mode", True))

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
        self._capture_btn.setText("⏳  Listening... (press key, Esc to cancel)")
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._cancel_key_capture)
        self._capture_timer.start(5000)

    def _cancel_key_capture(self) -> None:
        self._capturing_key = False
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
            self._capture_timer = None
        self._capture_btn.setText("🎹  Press a key to capture")

    def keyPressEvent(self, event) -> None:
        if self._capturing_key:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_key_capture()
                event.accept()
                return
            vk = event.nativeVirtualKey()
            if vk > 0:
                selected = -1
                for i in range(self._hotkey_combo.count()):
                    if self._hotkey_combo.itemData(i) == vk:
                        selected = i
                        break
                if selected == -1:
                    name = hotkey_name(vk) or f"Key_{vk}"
                    self._hotkey_combo.addItem(f"{name} ({hex(vk)})", vk)
                    selected = self._hotkey_combo.count() - 1
                self._hotkey_combo.setCurrentIndex(selected)
                self._cancel_key_capture()
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
        self._api_status.setStyleSheet("color: #fbbc04; font-size: 16px;")
        tester = _ApiKeyTester(api_key)
        tester.finished.connect(self._on_api_key_tested)
        tester.start()
        self._key_tester = tester

    def _on_api_key_tested(self, success: bool, msg: str) -> None:
        self._test_key_btn.setEnabled(True)
        self._test_key_btn.setText("Test Key")
        if success:
            self._api_status.setStyleSheet("color: #34a853; font-size: 16px;")
            QMessageBox.information(self, "API Key Test", msg)
        else:
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
        hotkey_val = self._hotkey_combo.currentData()
        self._settings.set("hotkey", int(hotkey_val) if hotkey_val is not None else 0x78)
        
        self._settings.save()
        self.saved.emit()
        self.close()