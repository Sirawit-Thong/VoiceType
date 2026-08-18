# voice_typing/ui/settings_window.py
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.config.settings import SettingsManager
from voice_typing.windows.hotkey import HOTKEY_OPTIONS, hotkey_name


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
        current = self._settings.get("hotkey", 0x78)
        self._hotkey_combo = QComboBox()
        selected = 0
        for i, (name, code) in enumerate(HOTKEY_OPTIONS):
            self._hotkey_combo.addItem(f"{name} ({hex(code)})", code)
            if code == current:
                selected = i
        if self._hotkey_combo.itemData(selected) != current:
            self._hotkey_combo.addItem(f"Custom ({hex(current)})", current)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)
        layout.addRow("Push-to-Talk key:", self._hotkey_combo)
        hint = QLabel(
            f"Currently using: {hotkey_name(current)} — "
            "press this key once to start recording, once to finalize and type."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a6;")
        layout.addRow("", hint)
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

        self._model = QLineEdit()
        self._model.setText(
            self._settings.get("model", "gemini-3.1-flash-live-preview")
        )
        layout.addRow("Model:", self._model)

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
        self._settings.set("model", self._model.text().strip())
        self._settings.set("fast_mode", self._fast_mode.isChecked())
        self._settings.set("hotkey", int(self._hotkey_combo.currentData()))
        self._settings.save()
        self.saved.emit()
        self.close()