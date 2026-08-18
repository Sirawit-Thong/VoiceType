# voice_typing/ui/settings_window.py
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
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
        raw_hotkey = self._hotkey_input.text().strip()
        try:
            hotkey = int(raw_hotkey, 0)
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Hotkey", "Hotkey must be a number or hex code, e.g. 0x7E."
            )
            return
        if not (0 <= hotkey <= 0xFFFF):
            QMessageBox.warning(
                self, "Invalid Hotkey", "Hotkey code must be between 0 and 0xFFFF."
            )
            return
        self._settings.set("hotkey", hotkey)
        self._settings.save()
        self.saved.emit()
        self.close()