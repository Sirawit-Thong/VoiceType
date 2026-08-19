# voice_typing/ui/status_bar.py
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QIcon, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
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
        # Keep the hide-and-ignore semantics, but let StatusBar.close() route
        # the hide through the fade-out animation instead of hiding instantly.
        self._on_close()
        event.ignore()


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


class _LevelMeter(QWidget):
    """5-segment microphone level meter.

    Painted in paintEvent so per-chunk audio level updates (~66 Hz) only
    trigger a repaint of 5 small rounded rects instead of stylesheet churn.
    """

    SEGMENT_COUNT = 5
    SEGMENT_WIDTH = 4
    SEGMENT_HEIGHT = 10
    SEGMENT_GAP = 2
    SEGMENT_RADIUS = 2
    LIT_COLOR = QColor("#e8eaed")
    DIM_COLOR = QColor(255, 255, 255, 38)  # rgba(255, 255, 255, 0.15)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        width = (
            self.SEGMENT_COUNT * self.SEGMENT_WIDTH
            + (self.SEGMENT_COUNT - 1) * self.SEGMENT_GAP
        )
        self.setFixedSize(width, self.SEGMENT_HEIGHT + 2)
        self.setToolTip("Microphone level")

    @property
    def lit_segments(self) -> int:
        """Number of lit segments for the current level, clamped to 0..5."""
        return max(
            0,
            min(
                self.SEGMENT_COUNT,
                int(self._level * self.SEGMENT_COUNT + 0.5),
            ),
        )

    def set_level(self, value: float) -> None:
        self._level = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        lit = self.lit_segments
        for i in range(self.SEGMENT_COUNT):
            painter.setBrush(self.LIT_COLOR if i < lit else self.DIM_COLOR)
            x = i * (self.SEGMENT_WIDTH + self.SEGMENT_GAP)
            y = (self.height() - self.SEGMENT_HEIGHT) // 2
            painter.drawRoundedRect(
                x,
                y,
                self.SEGMENT_WIDTH,
                self.SEGMENT_HEIGHT,
                self.SEGMENT_RADIUS,
                self.SEGMENT_RADIUS,
            )


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
        self._meter: _LevelMeter | None = None
        self._recording = False
        self._level = 0.0
        self._pulse_effect: QGraphicsOpacityEffect | None = None
        self._pulse_anim: QVariantAnimation | None = None
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
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
        win = _ControlWindow(self.close)
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
        self._pulse_effect = QGraphicsOpacityEffect(self._state_dot)
        self._pulse_effect.setOpacity(1.0)
        self._state_dot.setGraphicsEffect(self._pulse_effect)

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

        # Meter visibility follows the recording state captured at build time:
        # update_recording_state(True) may run before the window is built.
        self._meter = _LevelMeter()
        self._meter.set_level(self._level)
        self._meter.setVisible(self._recording)

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
        row.addWidget(self._meter)
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

    def set_level(self, value: float) -> None:
        """Update the mic level meter with a 0..1 value (clamped)."""
        self._level = max(0.0, min(1.0, value))
        if self._meter is not None:
            self._meter.set_level(self._level)

    def _start_pulse(self) -> None:
        if self._state_dot is None or self._pulse_effect is None:
            return
        if self._pulse_anim is not None:
            return  # already pulsing; do not restart on every partial transcript
        anim = QVariantAnimation(self._state_dot)
        anim.setStartValue(0.4)
        anim.setEndValue(1.0)
        anim.setDuration(350)  # 350ms up + 350ms down ~= 700ms period
        anim.setLoopCount(-1)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.valueChanged.connect(self._pulse_effect.setOpacity)
        self._pulse_anim = anim
        anim.start()

    def _stop_pulse(self) -> None:
        if self._pulse_anim is not None:
            anim, self._pulse_anim = self._pulse_anim, None
            anim.stop()
            anim.deleteLater()
        if self._pulse_effect is not None:
            self._pulse_effect.setOpacity(1.0)

    def _cancel_fade_in(self) -> None:
        if self._fade_in_anim is not None:
            anim, self._fade_in_anim = self._fade_in_anim, None
            anim.stop()
            anim.deleteLater()

    def _cancel_fade_out(self) -> None:
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.stop()
            anim.deleteLater()

    def _on_fade_in_finished(self) -> None:
        if self._fade_in_anim is not None:
            anim, self._fade_in_anim = self._fade_in_anim, None
            anim.deleteLater()

    def _finish_close(self) -> None:
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.deleteLater()
        self._stop_pulse()
        if self._window is not None:
            self._window.hide()
            self._window = None
            self._state_dot = None
            self._pulse_effect = None
            self._mic_button = None
            self._status_label = None
            self._menu_button = None
            self._meter = None

    def show(self) -> None:
        if self._window is None:
            self._window = self._build_window()
            self._window.setWindowOpacity(0.0)
            if self._saved_position is not None:
                self._window.move(*self._saved_position)
            else:
                self._move_bottom_center()
        # Repeated show() during a fade-out: cancel it and fade back in.
        self._cancel_fade_out()
        self._cancel_fade_in()
        self._window.show()
        self._window.raise_()
        # Fade in unless already fully opaque (repeated show() while visible
        # must not restart the animation and cause a flash).
        if self._window.windowOpacity() < 1.0:
            anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
            anim.setDuration(150)
            anim.setStartValue(self._window.windowOpacity())
            anim.setEndValue(1.0)
            anim.finished.connect(self._on_fade_in_finished)
            self._fade_in_anim = anim
            anim.start()

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
        if self._meter is not None:
            if recording:
                self._meter.show()
            else:
                self._meter.hide()
        if not recording:
            self._stop_pulse()

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
        if state == "listening":
            self._start_pulse()
        else:
            self._stop_pulse()

    def hide(self) -> None:
        if self._window is not None:
            self._window.hide()

    def close(self) -> None:
        if self._window is None:
            return
        if self._fade_out_anim is not None:
            return  # already fading out; guard against re-entrancy
        self._cancel_fade_in()
        self._stop_pulse()
        anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
        anim.setDuration(120)
        anim.setStartValue(self._window.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish_close)
        self._fade_out_anim = anim
        anim.start()