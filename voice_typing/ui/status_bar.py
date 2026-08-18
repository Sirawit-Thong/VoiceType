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