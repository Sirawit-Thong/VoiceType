# voice_typing/ui/status_bar.py
from __future__ import annotations

import math
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
from PySide6.QtGui import (
    QAction,
    QColor,
    QEnterEvent,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
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
from voice_typing.config.settings import get_asset_path


class StatusBarSignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    language_changed = Signal(str)


class _ControlWindow(QWidget):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._on_close()
        event.ignore()


class _WaveVisualizer(QWidget):
    """Modern 5-bar animated audio wave visualizer."""

    BAR_COUNT = 5
    BAR_WIDTH = 3
    BAR_GAP = 2
    MAX_BAR_HEIGHT = 16
    MIN_BAR_HEIGHT = 3
    BAR_RADIUS = 1.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._color = QColor("#34a853")
        width = self.BAR_COUNT * self.BAR_WIDTH + (self.BAR_COUNT - 1) * self.BAR_GAP
        self.setFixedSize(width, self.MAX_BAR_HEIGHT)
        self.setToolTip("Audio waveform")

    def set_level(self, value: float) -> None:
        self._level = max(0.0, min(1.0, value))
        self.update()

    def set_color(self, color_hex: str) -> None:
        self._color = QColor(color_hex)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)

        center_idx = self.BAR_COUNT // 2
        for i in range(self.BAR_COUNT):
            dist_from_center = abs(i - center_idx)
            factor = 1.0 - (dist_from_center * 0.22)
            bar_h = self.MIN_BAR_HEIGHT + (self.MAX_BAR_HEIGHT - self.MIN_BAR_HEIGHT) * self._level * factor
            bar_h = max(self.MIN_BAR_HEIGHT, min(float(self.MAX_BAR_HEIGHT), bar_h))
            x = i * (self.BAR_WIDTH + self.BAR_GAP)
            y = (self.height() - bar_h) / 2.0
            painter.drawRoundedRect(
                x,
                y,
                self.BAR_WIDTH,
                bar_h,
                self.BAR_RADIUS,
                self.BAR_RADIUS,
            )


class _DraggableCapsule(QFrame):
    drag_finished = Signal(int, int)
    hover_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None

    def enterEvent(self, event: QEnterEvent) -> None:
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hover_changed.emit(False)
        super().leaveEvent(event)

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
    EXPANDED_WIDTH = 205
    COLLAPSED_WIDTH = 38
    CAPSULE_HEIGHT = 36

    def __init__(
        self,
        on_position_changed: Callable[[int, int], None] | None = None,
        saved_position: tuple[int, int] | None = None,
        style: str = "pill",
    ) -> None:
        self.signals = StatusBarSignals()
        self._style = style  # "pill" or "dot"
        self._window: _ControlWindow | None = None
        self._capsule: _DraggableCapsule | None = None
        self._state_dot: QLabel | None = None
        self._mic_button: QPushButton | None = None
        self._wave: _WaveVisualizer | None = None
        self._status_label: QLabel | None = None
        self._menu_button: QPushButton | None = None
        self._recording = False
        self._hovered = False
        self._level = 0.0
        self._state_color = "#34a853"
        self._pulse_effect: QGraphicsOpacityEffect | None = None
        self._pulse_anim: QVariantAnimation | None = None
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._size_anim: QVariantAnimation | None = None
        self._hotkey_name = "F9"
        self._on_position_changed = on_position_changed
        self._saved_position = saved_position
        self._opacity: float = 0.94
        self._language: str = "auto"

    @property
    def style(self) -> str:
        return self._style

    def set_style(self, style: str) -> None:
        self._style = "dot" if style == "dot" else "pill"
        self._update_layout_for_state()

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.5, min(1.0, value))
        if self._window is not None:
            self._window.setWindowOpacity(self._opacity)

    def set_language(self, lang: str) -> None:
        self._language = lang

    def set_hotkey_name(self, name: str) -> None:
        self._hotkey_name = name
        self._update_hint()

    def _update_hint(self) -> None:
        if self._status_label is not None and not self._recording:
            self._status_label.setText(f"{self._hotkey_name}")

    def _make_mic_pixmap(self, color: str) -> QPixmap:
        pixmap = QPixmap(18, 18)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(color), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(5, 6, 8, 8, 0, -180 * 16)
        painter.drawLine(9, 13, 9, 16)
        painter.drawLine(6, 16, 12, 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(7, 2, 4, 7, 2, 2)
        painter.end()
        return pixmap

    def _build_window(self) -> _ControlWindow:
        win = _ControlWindow(self.close)
        win.setWindowTitle("VoiceType")
        icon_path = get_asset_path("icon.ico")
        if not icon_path.exists():
            icon_path = get_asset_path("icon.png")
        if icon_path.exists():
            win.setWindowIcon(QIcon(str(icon_path)))
        win.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        win.setFixedHeight(self.CAPSULE_HEIGHT)
        win.setFixedWidth(self.EXPANDED_WIDTH)

        capsule = _DraggableCapsule(win)
        self._capsule = capsule
        capsule.setObjectName("capsule")
        capsule.setCursor(Qt.CursorShape.OpenHandCursor)
        capsule.setStyleSheet(
            "#capsule { background-color: rgba(20, 21, 24, 0.94); "
            "border-radius: 18px; border: 1px solid rgba(255, 255, 255, 0.12); }"
        )
        capsule.drag_finished.connect(self._on_drag_finished)
        capsule.hover_changed.connect(self._on_hover_changed)

        self._mic_button = QPushButton()
        self._mic_button.setIcon(QIcon(self._make_mic_pixmap(self._state_color)))
        self._mic_button.setIconSize(QSize(18, 18))
        self._mic_button.setFixedSize(24, 24)
        self._mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_button.setToolTip("Start / Stop recording")
        self._mic_button.setStyleSheet(
            "QPushButton { background: transparent; border: none; border-radius: 12px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.15); }"
        )
        self._mic_button.clicked.connect(self._on_toggle)

        self._pulse_effect = QGraphicsOpacityEffect(self._mic_button)
        self._pulse_effect.setOpacity(1.0)
        self._mic_button.setGraphicsEffect(self._pulse_effect)

        self._wave = _WaveVisualizer()
        self._wave.set_color(self._state_color)
        self._wave.set_level(self._level)

        self._status_label = QLabel("")
        self._status_label.setMaximumWidth(100)
        self._status_label.setStyleSheet("color: #e8eaed; font-size: 12px; font-weight: 500;")

        self._menu_button = QPushButton("⋯")
        self._menu_button.setFixedSize(20, 20)
        self._menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_button.setToolTip("Menu")
        self._menu_button.setStyleSheet(
            "QPushButton { background: transparent; color: #9aa0a6; border: none; "
            "border-radius: 10px; font-size: 14px; font-weight: bold; padding-bottom: 2px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.12); "
            "color: #e8eaed; }"
        )
        self._menu_button.clicked.connect(self._show_menu)

        row = QHBoxLayout(capsule)
        row.setContentsMargins(6, 0, 8, 0)
        row.setSpacing(6)
        row.addWidget(self._mic_button)
        row.addWidget(self._wave)
        row.addWidget(self._status_label)
        row.addStretch(1)
        row.addWidget(self._menu_button)

        root = QVBoxLayout(win)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(capsule)
        self._update_hint()
        self._update_layout_for_state()
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
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self.signals.open_settings.emit)
        menu.addAction(settings_action)

        lang_menu = menu.addMenu("🌐 Language")
        for code, label in [
            ("auto", "Auto (Thai + English)"),
            ("thai", "Thai (ภาษาไทย)"),
            ("english", "English"),
        ]:
            action = QAction(label, lang_menu)
            action.setCheckable(True)
            action.setChecked(self._language == code)
            action.triggered.connect(
                lambda checked=False, c=code: self.signals.language_changed.emit(c)
            )
            lang_menu.addAction(action)

        test_action = QAction("Test Microphone", menu)
        test_action.triggered.connect(self.signals.test_microphone.emit)
        menu.addAction(test_action)
        menu.addSeparator()
        exit_action = QAction("Exit", menu)
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

    def _on_hover_changed(self, hovered: bool) -> None:
        self._hovered = hovered
        if self._style == "dot":
            self._update_layout_for_state()

    def _update_layout_for_state(self) -> None:
        if self._window is None:
            return
        should_expand = (self._style == "pill") or self._recording or self._hovered
        target_width = self.EXPANDED_WIDTH if should_expand else self.COLLAPSED_WIDTH

        if self._wave is not None:
            self._wave.setVisible(should_expand)
        if self._status_label is not None:
            self._status_label.setVisible(should_expand)
        if self._menu_button is not None:
            self._menu_button.setVisible(should_expand)

        self._animate_width(target_width)

    def _animate_width(self, target_width: int) -> None:
        if self._window is None or self._window.width() == target_width:
            return
        if self._size_anim is not None:
            self._size_anim.stop()
            self._size_anim.deleteLater()
        anim = QVariantAnimation(self._window)
        anim.setStartValue(self._window.width())
        anim.setEndValue(target_width)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_width_animated)
        self._size_anim = anim
        anim.start()

    def _on_width_animated(self, value: int) -> None:
        if self._window is not None:
            self._window.setFixedWidth(int(value))

    def _on_drag_finished(self, x: int, y: int) -> None:
        if self._on_position_changed is not None:
            self._on_position_changed(x, y)

    def set_level(self, value: float) -> None:
        self._level = max(0.0, min(1.0, value))
        if self._wave is not None:
            self._wave.set_level(self._level)

    def _start_pulse(self) -> None:
        if self._mic_button is None or self._pulse_effect is None:
            return
        if self._pulse_anim is not None:
            return
        anim = QVariantAnimation(self._mic_button)
        anim.setStartValue(0.4)
        anim.setEndValue(1.0)
        anim.setDuration(350)
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
        # Apply stored opacity after fade-in
        if self._window is not None:
            self._window.setWindowOpacity(self._opacity)

    def _finish_close(self) -> None:
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.deleteLater()
        self._stop_pulse()
        if self._window is not None:
            self._window.hide()
            self._window = None
            self._capsule = None
            self._mic_button = None
            self._pulse_effect = None
            self._wave = None
            self._status_label = None
            self._menu_button = None

    def show(self) -> None:
        if self._window is None:
            self._window = self._build_window()
            self._window.setWindowOpacity(0.0)
            if self._saved_position is not None:
                self._window.move(*self._saved_position)
            else:
                self._move_bottom_center()
        self._cancel_fade_out()
        self._cancel_fade_in()
        self._window.show()
        self._window.raise_()
        if self._window.windowOpacity() < self._opacity:
            anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
            anim.setDuration(150)
            anim.setStartValue(self._window.windowOpacity())
            anim.setEndValue(self._opacity)
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
        x = (geo.width() - self.EXPANDED_WIDTH) // 2 + geo.x()
        y = geo.height() - self.CAPSULE_HEIGHT - 30 + geo.y()
        self._window.move(x, y)

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        if self._mic_button is not None:
            self._mic_button.setToolTip(
                "Stop recording" if recording else "Start / Stop recording"
            )
        if not recording:
            self._stop_pulse()
        self._update_layout_for_state()

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
        self._state_color = color
        title = titles.get(state, state.title())
        if self._mic_button is not None:
            self._mic_button.setIcon(QIcon(self._make_mic_pixmap(color)))
        if self._wave is not None:
            self._wave.set_color(color)
        if self._status_label is not None:
            if state == "ready" and not text:
                self._update_hint()
            elif text:
                shown = text if len(text) <= 16 else text[:14] + ".."
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
            return
        self._cancel_fade_in()
        self._stop_pulse()
        anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
        anim.setDuration(120)
        anim.setStartValue(self._window.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish_close)
        self._fade_out_anim = anim
        anim.start()