# voice_typing/ui/status_bar.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class StatusBarSignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()


class _ControlWindow(QWidget):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._on_close()
        event.ignore()
        self.hide()


class _DraggableCapsule(QFrame):
    drag_finished = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.window().frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.window().move(
                event.globalPosition().toPoint() - self._drag_offset
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            win = self.window()
            self.drag_finished.emit(win.x(), win.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class StatusBar:
    def __init__(
        self,
        on_position_changed: Callable[[int, int], None] | None = None,
        saved_position: tuple[int, int] | None = None,
    ) -> None:
        self.signals = StatusBarSignals()
        self._window: _ControlWindow | None = None
        self._state_dot: QLabel | None = None
        self._mic_button: QPushButton | None = None
        self._status_label: QLabel | None = None
        self._menu_button: QPushButton | None = None
        self._recording = False
        self._hotkey_name = "F9"
        self._on_position_changed = on_position_changed
        self._saved_position = saved_position

    def set_hotkey_name(self, name: str) -> None:
        self._hotkey_name = name
        self._update_hint()

    def _update_hint(self) -> None:
        if self._status_label is not None and not self._recording:
            self._status_label.setText(f"Press {self._hotkey_name} to record")

    def _make_mic_pixmap(self, color: str) -> QPixmap:
        pixmap = QPixmap(22, 22)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(color), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(7, 8, 8, 8, 0, -180 * 16)
        painter.drawLine(11, 16, 11, 19)
        painter.drawLine(8, 19, 14, 19)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(9, 3, 4, 8, 2, 2)
        painter.end()
        return pixmap

    def _build_window(self) -> _ControlWindow:
        win = _ControlWindow(self.hide)
        win.setWindowTitle("VoiceType")
        win.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        win.setFixedSize(262, 50)

        capsule = _DraggableCapsule(win)
        capsule.setObjectName("capsule")
        capsule.setCursor(Qt.CursorShape.OpenHandCursor)
        capsule.setStyleSheet(
            "#capsule { background-color: rgba(32, 33, 36, 0.95); "
            "border-radius: 22px; border: 1px solid rgba(255, 255, 255, 0.12); }"
        )
        capsule.drag_finished.connect(self._on_drag_finished)

        self._state_dot = QLabel("●")
        self._state_dot.setStyleSheet("color: #34a853; font-size: 14px;")

        self._mic_button = QPushButton()
        self._mic_button.setIcon(QIcon(self._make_mic_pixmap("#e8eaed")))
        self._mic_button.setIconSize(QSize(22, 22))
        self._mic_button.setFixedSize(28, 28)
        self._mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_button.setToolTip("Start / Stop recording")
        self._mic_button.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 14px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.12); }"
        )
        self._mic_button.clicked.connect(self._on_toggle)

        self._status_label = QLabel("")
        self._status_label.setMaximumWidth(130)
        self._status_label.setStyleSheet("color: #e8eaed; font-size: 13px;")

        self._menu_button = QPushButton("⋯")
        self._menu_button.setFixedSize(28, 28)
        self._menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_button.setToolTip("Menu")
        self._menu_button.setStyleSheet(
            "QPushButton { background: transparent; color: #bdc1c6; border: none; "
            "border-radius: 14px; font-size: 18px; font-weight: bold; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.12); "
            "color: #e8eaed; }"
        )
        self._menu_button.clicked.connect(self._show_menu)

        row = QHBoxLayout(capsule)
        row.setContentsMargins(14, 0, 6, 0)
        row.setSpacing(8)
        row.addWidget(self._state_dot)
        row.addWidget(self._mic_button)
        row.addWidget(self._status_label)
        row.addStretch(1)
        row.addWidget(self._menu_button)

        root = QVBoxLayout(win)
        root.setContentsMargins(6, 6, 6, 6)
        root.addWidget(capsule)
        self._update_hint()
        return win

    def _show_menu(self) -> None:
        if self._menu_button is None:
            return
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background-color: #202124; color: #e8eaed; "
            "border: 1px solid #3c4043; border-radius: 8px; padding: 6px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 6px; }"
            "QMenu::item:selected { background-color: #303134; }"
            "QMenu::separator { height: 1px; background-color: #3c4043; "
            "margin: 4px 8px; }"
        )
        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.signals.open_settings.emit)
        menu.addAction(settings_action)
        test_action = QAction("Test Microphone")
        test_action.triggered.connect(self.signals.test_microphone.emit)
        menu.addAction(test_action)
        menu.addSeparator()
        exit_action = QAction("Exit")
        exit_action.triggered.connect(self.signals.exit_app.emit)
        menu.addAction(exit_action)
        menu.exec(
            self._menu_button.mapToGlobal(QPoint(0, self._menu_button.height()))
        )

    def _on_toggle(self) -> None:
        if self._recording:
            self.signals.stop_recording.emit()
        else:
            self.signals.start_recording.emit()

    def _on_drag_finished(self, x: int, y: int) -> None:
        if self._on_position_changed is not None:
            self._on_position_changed(x, y)

    def show(self) -> None:
        if self._window is None:
            self._window = self._build_window()
            if self._saved_position is not None:
                self._window.move(*self._saved_position)
            else:
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
        y = geo.height() - self._window.height() - 30 + geo.y()
        self._window.move(x, y)

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        if self._mic_button is not None:
            self._mic_button.setToolTip(
                "Stop recording" if recording else "Start / Stop recording"
            )

    def set_state(self, state: str, text: str = "") -> None:
        colors = {
            "ready": "#34a853",
            "listening": "#ea4335",
            "processing": "#fbbc04",
            "error": "#9aa0a6",
        }
        titles = {
            "ready": "Ready",
            "listening": "Listening...",
            "processing": "Processing...",
            "error": "Error",
        }
        color = colors.get(state, "#9aa0a6")
        title = titles.get(state, state.title())
        if self._state_dot is not None:
            self._state_dot.setStyleSheet(f"color: {color}; font-size: 14px;")
        if self._mic_button is not None:
            self._mic_button.setIcon(QIcon(self._make_mic_pixmap(color)))
        if self._status_label is not None:
            if state == "ready" and not text:
                self._update_hint()
            elif text:
                shown = text if len(text) <= 20 else text[:17] + "..."
                self._status_label.setText(shown)
            else:
                self._status_label.setText(title)
        if self._window is not None:
            self._window.setToolTip(text if text else title)

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def close(self) -> None:
        if self._window is not None:
            self._window.hide()
            self._window = None
            self._state_dot = None
            self._mic_button = None
            self._status_label = None
            self._menu_button = None