# voice_typing/ui/status_bar.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class StatusBarSignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    exit_app = Signal()


class _ControlWindow(QWidget):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._on_close()
        event.ignore()
        self.hide()


class StatusBar:
    def __init__(self) -> None:
        self.signals = StatusBarSignals()
        self._window: _ControlWindow | None = None
        self._status_label: QLabel | None = None
        self._transcript_label: QLabel | None = None
        self._toggle_button: QPushButton | None = None
        self._recording = False

    def _build_window(self) -> _ControlWindow:
        win = _ControlWindow(self.hide)
        win.setWindowTitle("VoiceType")
        win.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        win.resize(380, 160)
        win.setStyleSheet("QWidget { background-color: #202124; color: #e8eaed; }")

        self._status_label = QLabel("🟢 Ready")
        self._status_label.setStyleSheet("font-size: 15px; font-weight: bold;")

        self._transcript_label = QLabel("Press F9 or click Start to record.")
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._transcript_label.setStyleSheet("color: #bdc1c6; font-size: 13px;")

        self._toggle_button = QPushButton("Start Recording")
        self._toggle_button.clicked.connect(self._on_toggle)
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.signals.open_settings.emit)
        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.signals.exit_app.emit)

        buttons = QHBoxLayout()
        buttons.addWidget(self._toggle_button)
        buttons.addWidget(settings_button)
        buttons.addWidget(exit_button)

        layout = QVBoxLayout(win)
        layout.addWidget(self._status_label)
        layout.addWidget(self._transcript_label, 1)
        layout.addLayout(buttons)
        return win

    def _on_toggle(self) -> None:
        if self._recording:
            self.signals.stop_recording.emit()
        else:
            self.signals.start_recording.emit()

    def show(self) -> None:
        if self._window is None:
            self._window = self._build_window()
            self._move_bottom_center()
        self._window.show()
        self._window.raise_()

    def _move_bottom_center(self) -> None:
        if self._window is None:
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = (geo.width() - self._window.width()) // 2 + geo.x()
        y = geo.height() - self._window.height() - 40 + geo.y()
        self._window.move(x, y)

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        if self._toggle_button is not None:
            self._toggle_button.setText(
                "Stop Recording" if recording else "Start Recording"
            )

    def set_state(self, state: str, text: str = "") -> None:
        icons = {"ready": "🟢", "listening": "🔴", "processing": "⚡", "error": "⚪"}
        icon = icons.get(state, "⚪")
        titles = {
            "ready": "Ready",
            "listening": "Listening",
            "processing": "Processing",
            "error": "Error",
        }
        title = titles.get(state, state.title())
        if self._status_label is not None:
            self._status_label.setText(f"{icon} {title}")
        if text and self._transcript_label is not None:
            self._transcript_label.setText(text)

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def close(self) -> None:
        if self._window is not None:
            self._window.hide()
            self._window = None
            self._status_label = None
            self._transcript_label = None
            self._toggle_button = None
