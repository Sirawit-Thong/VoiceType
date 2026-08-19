# voice_typing/ui/status_bar.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
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
        self._hotkey_name = "F9"

    def set_hotkey_name(self, name: str) -> None:
        self._hotkey_name = name
        self._update_hint()

    def _update_hint(self) -> None:
        if self._transcript_label is not None and not self._recording:
            self._transcript_label.setText(
                f"Press {self._hotkey_name} or click Start to record."
            )

    def _build_window(self) -> _ControlWindow:
        win = _ControlWindow(self.hide)
        win.setWindowTitle("VoiceType")
        win.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        win.resize(400, 175)

        frame = QFrame(win)
        frame.setObjectName("card")
        frame.setStyleSheet(
            "#card { background-color: rgba(32, 33, 36, 0.95); border-radius: 14px; "
            "border: 1px solid rgba(255, 255, 255, 0.10); }"
        )

        self._status_label = QLabel("🟢 Ready")
        self._status_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #e8eaed;"
        )

        self._transcript_label = QLabel("")
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._transcript_label.setStyleSheet("color: #bdc1c6; font-size: 13px;")

        self._toggle_button = QPushButton("Start Recording")
        self._toggle_button.clicked.connect(self._on_toggle)
        self._toggle_button.setStyleSheet(
            "QPushButton { background-color: #1a73e8; color: #ffffff; border: none; "
            "border-radius: 8px; padding: 6px 12px; font-size: 13px; }"
            "QPushButton:hover { background-color: #2b84f5; }"
        )
        settings_button = QPushButton("Settings")
        settings_button.clicked.connect(self.signals.open_settings.emit)
        settings_button.setStyleSheet(
            "QPushButton { background-color: #303134; color: #e8eaed; border: none; "
            "border-radius: 8px; padding: 6px 12px; font-size: 13px; }"
            "QPushButton:hover { background-color: #3c4043; }"
        )
        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.signals.exit_app.emit)
        exit_button.setStyleSheet(settings_button.styleSheet())

        buttons = QHBoxLayout()
        buttons.addWidget(self._toggle_button)
        buttons.addWidget(settings_button)
        buttons.addWidget(exit_button)

        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.addWidget(self._status_label)
        card_layout.addWidget(self._transcript_label, 1)
        card_layout.addLayout(buttons)

        root = QVBoxLayout(win)
        root.setContentsMargins(10, 10, 10, 10)
        root.addWidget(frame)
        self._update_hint()
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
        if not recording:
            self._update_hint()

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
