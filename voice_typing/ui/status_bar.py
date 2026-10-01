# voice_typing/ui/status_bar.py
from __future__ import annotations

import logging
import math
from typing import Callable

log = logging.getLogger(__name__)

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
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from voice_typing.config.settings import get_asset_path
from voice_typing.ui._theme import (
    MENU_STYLESHEET,
    CAPSULE_HEIGHT as THEME_CAPSULE_HEIGHT,
    COLOR_ERROR_DEAD,
    COLOR_LISTENING,
    COLOR_PROCESSING,
    COLOR_READY,
    COLOR_RECONNECTING,
    COLOR_TEXT_PRIMARY,
    FONT_FAMILY,
    FONT_SIZE_STATUS,
    FONT_WEIGHT_STATUS,
    OPACITY_DEFAULT,
    OPACITY_IDLE_WAVE_DIM,
    RADIUS_CAPSULE as THEME_RADIUS_CAPSULE,
    TOUCH_TARGET_MIN,
    capsule_stylesheet,
    control_button_stylesheet,
)


# Canonical capsule states with legacy aliases.
# ready -> idle, error -> error-dead. processing is retained as its own state.
STATE_ALIASES = {
    "ready": "idle",
    "error": "error-dead",
}

STATE_COLORS = {
    "idle": COLOR_READY,
    "listening": COLOR_LISTENING,
    "processing": COLOR_PROCESSING,
    "reconnecting": COLOR_RECONNECTING,
    "error-dead": COLOR_ERROR_DEAD,
}

STATE_TITLES = {
    "idle": "Ready",
    "listening": "Listening...",
    "processing": "Processing...",
    "reconnecting": "Reconnecting...",
    "error-dead": "Error - check connection",
}

STATE_MIC_TOOLTIPS = {
    "idle": "Ready - press hotkey or click mic to record",
    "listening": "Stop recording",
    "processing": "Processing - please wait...",
    "reconnecting": "Reconnecting - please wait, recording will resume automatically",
    "error-dead": "Connection failed - check API key and network, then press hotkey to retry",
}

# Mic is non-interactive while the engine cannot record.
MIC_DISABLED_STATES = frozenset({"reconnecting", "error-dead"})

# Border highlight draws attention to live/transient states only.
HIGHLIGHT_STATES = frozenset({"listening", "reconnecting"})

# Pulse draws attention to live/transient states only.
PULSE_STATES = frozenset({"listening", "reconnecting"})


class StatusBarSignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    language_changed = Signal(str)
    toggle_overlay = Signal()


class _ControlWindow(QWidget):
    def __init__(self, on_close: Callable[[], None]) -> None:
        super().__init__()
        self._on_close = on_close

    def closeEvent(self, event) -> None:
        self._on_close()
        event.ignore()


class _WaveVisualizer(QWidget):
    """Modern 5-bar level meter; active while audio flows (no idle capture)."""

    BAR_COUNT = 5
    BAR_WIDTH = 3
    BAR_GAP = 2
    MAX_BAR_HEIGHT = 16
    MIN_BAR_HEIGHT = 3
    BAR_RADIUS = 1.5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = 0.0
        self._color = QColor(COLOR_READY)
        width = self.BAR_COUNT * self.BAR_WIDTH + (self.BAR_COUNT - 1) * self.BAR_GAP
        self.setFixedSize(width, self.MAX_BAR_HEIGHT)
        self.setToolTip("Level meter active while audio flows")

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
        self._wave_opacity: QGraphicsOpacityEffect | None = None
        self._status_label: QLabel | None = None
        self._menu_button: QPushButton | None = None
        self._tray_btn: QPushButton | None = None
        self._row: QHBoxLayout | None = None
        self._recording = False
        self._hovered = False
        self._level = 0.0
        self._state = "idle"
        self._state_color = COLOR_READY
        self._pulse_effect: QGraphicsOpacityEffect | None = None
        self._pulse_anim: QVariantAnimation | None = None
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._size_anim: QVariantAnimation | None = None
        self._hotkey_name = "F9"
        self._on_position_changed = on_position_changed
        self._saved_position = saved_position
        self._opacity: float = OPACITY_DEFAULT
        self._language: str = "auto"
        self._overlay_enabled: bool = True
        self._pending_text: str = ""
        # Geometry parity with theme tokens is verified by tests
        # (test_theme_tokens / test_status_bar); log instead of asserting
        # so a mismatch never crashes the UI at runtime.
        if self.CAPSULE_HEIGHT != THEME_CAPSULE_HEIGHT:
            log.warning(
                "StatusBar CAPSULE_HEIGHT %s != theme %s; using class value",
                self.CAPSULE_HEIGHT,
                THEME_CAPSULE_HEIGHT,
            )
        if THEME_RADIUS_CAPSULE != 18:
            log.warning(
                "Theme RADIUS_CAPSULE changed (%s); capsule styling may drift",
                THEME_RADIUS_CAPSULE,
            )

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

    def set_overlay_enabled(self, enabled: bool) -> None:
        """Update the 'Show Transcript' toggle check state in the menu."""
        self._overlay_enabled = enabled
        if hasattr(self, "_overlay_toggle_action") and self._overlay_toggle_action is not None:
            self._overlay_toggle_action.setChecked(enabled)

    def set_hotkey_name(self, name: str) -> None:
        self._hotkey_name = name
        self._update_hint()

    def _update_hint(self) -> None:
        if self._status_label is not None and not self._recording:
            self._status_label.setText(f"{self._hotkey_name}")

    def _make_mic_pixmap(self, color: str) -> QPixmap:
        # Logical icon size stays 18x18; physical pixels scale with DPR so
        # the glyph stays crisp (and centered) on HiDPI displays.
        logical = 18
        dpr = 1.0
        app = QApplication.instance()
        if app is not None:
            try:
                screen = app.primaryScreen()
                if screen is not None:
                    dpr = float(screen.devicePixelRatio() or 1.0)
            except Exception:
                dpr = 1.0
        if dpr < 1.0:
            dpr = 1.0
        pixmap = QPixmap(max(1, round(logical * dpr)), max(1, round(logical * dpr)))
        pixmap.setDevicePixelRatio(dpr)
        transparent = QColor(Qt.GlobalColor.transparent)
        pixmap.fill(transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if dpr != 1.0:
            painter.scale(dpr, dpr)
        painter.setPen(QPen(QColor(color), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(5, 6, 8, 8, 0, -180 * 16)
        # Stem + base sit 1px higher than before so the glyph bounding box
        # (y 2..15) is vertically centered in the 18px pixmap (margins 2/2).
        painter.drawLine(9, 12, 9, 15)
        painter.drawLine(6, 15, 12, 15)
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
        capsule.setStyleSheet(capsule_stylesheet())
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        capsule.setGraphicsEffect(shadow)
        capsule.drag_finished.connect(self._on_drag_finished)
        capsule.hover_changed.connect(self._on_hover_changed)

        self._mic_button = QPushButton()
        self._mic_button.setIcon(QIcon(self._make_mic_pixmap(self._state_color)))
        self._mic_button.setIconSize(QSize(18, 18))
        self._mic_button.setFixedSize(TOUCH_TARGET_MIN, TOUCH_TARGET_MIN)
        self._mic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._mic_button.setToolTip(STATE_MIC_TOOLTIPS["idle"])
        self._mic_button.setStyleSheet(control_button_stylesheet())
        self._mic_button.clicked.connect(self._on_toggle)

        self._pulse_effect = QGraphicsOpacityEffect(self._mic_button)
        self._pulse_effect.setOpacity(1.0)
        self._mic_button.setGraphicsEffect(self._pulse_effect)

        self._wave = _WaveVisualizer()
        self._wave.set_color(self._state_color)
        self._wave.set_level(self._level)
        self._wave_opacity = QGraphicsOpacityEffect(self._wave)
        self._wave_opacity.setOpacity(OPACITY_IDLE_WAVE_DIM)
        self._wave.setGraphicsEffect(self._wave_opacity)

        self._status_label = QLabel("")
        self._status_label.setMaximumWidth(100)
        self._status_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; "
            f"font-size: {FONT_SIZE_STATUS}px; "
            f"font-weight: {FONT_WEIGHT_STATUS}; "
            f"font-family: {FONT_FAMILY};"
        )

        self._tray_btn = QPushButton("─")
        self._tray_btn.setObjectName("tray_btn")
        self._tray_btn.setFixedSize(TOUCH_TARGET_MIN, TOUCH_TARGET_MIN)
        self._tray_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tray_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._tray_btn.setToolTip("Minimize to tray")
        self._tray_btn.setStyleSheet(control_button_stylesheet())
        self._tray_btn.clicked.connect(self._minimize_to_tray)

        self._menu_button = QPushButton("⋯")
        self._menu_button.setFixedSize(TOUCH_TARGET_MIN, TOUCH_TARGET_MIN)
        self._menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._menu_button.setToolTip("Menu")
        self._menu_button.setStyleSheet(control_button_stylesheet())
        self._menu_button.clicked.connect(self._show_menu)

        row = QHBoxLayout(capsule)
        row.setContentsMargins(6, 0, 8, 0)
        row.setSpacing(6)
        row.addWidget(self._mic_button)
        row.addWidget(self._wave)
        row.addWidget(self._status_label)
        row.addStretch(1)
        row.addWidget(self._tray_btn)
        row.addWidget(self._menu_button)
        self._row = row

        root = QVBoxLayout(win)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(capsule)
        self._update_hint()
        self._update_layout_for_state()
        self._apply_state_visuals(self._state, self._pending_text)
        return win

    def _show_menu(self) -> None:
        if self._menu_button is None:
            return
        menu = QMenu(self._window)
        menu.setStyleSheet(MENU_STYLESHEET)
        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self.signals.open_settings.emit)
        menu.addAction(settings_action)

        lang_menu = menu.addMenu("🌐 Language")
        from voice_typing.config.settings import SUPPORTED_LANGUAGES
        for code, label in SUPPORTED_LANGUAGES:
            action = QAction(label, lang_menu)
            action.setCheckable(True)
            action.setChecked(self._language == code)
            action.triggered.connect(
                lambda checked=False, c=code: self.signals.language_changed.emit(c)
            )
            lang_menu.addAction(action)

        menu.addSeparator()

        self._overlay_toggle_action = QAction("Show Transcript", menu)
        self._overlay_toggle_action.setCheckable(True)
        self._overlay_toggle_action.setChecked(True)
        self._overlay_toggle_action.triggered.connect(self.signals.toggle_overlay.emit)
        menu.addAction(self._overlay_toggle_action)

        menu.addSeparator()

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

    def _minimize_to_tray(self) -> None:
        """Hide status bar and let tray icon handle interaction."""
        self._window.hide()

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
        if self._tray_btn is not None:
            self._tray_btn.setVisible(should_expand)

        # Dot mode shows only the 28px mic in a 38px capsule. The QFrame
        # carries 1px contents margins on each side, so row margins of 4
        # (1+4+28+4+1=38) keep the button exactly centered; pill mode
        # keeps the roomier 6/8 margins.
        if self._row is not None:
            if should_expand:
                self._row.setContentsMargins(6, 0, 8, 0)
            else:
                self._row.setContentsMargins(4, 0, 4, 0)

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
            self._wave_opacity = None
            self._status_label = None
            self._menu_button = None
            self._tray_btn = None
            self._row = None

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
        y = geo.height() - self.CAPSULE_HEIGHT - CAPSULE_BOTTOM_MARGIN + geo.y()
        self._window.move(x, y)

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        if self._mic_button is not None and self._mic_button.isEnabled():
            self._mic_button.setToolTip(
                "Stop recording" if recording else "Start / Stop recording"
            )
        if not recording:
            self._stop_pulse()
        self._update_layout_for_state()

    def _apply_state_visuals(self, canonical: str, text: str) -> None:
        color = STATE_COLORS[canonical]
        self._state = canonical
        self._state_color = color
        if self._capsule is not None:
            accent = color if canonical in HIGHLIGHT_STATES else None
            self._capsule.setStyleSheet(capsule_stylesheet(accent))
        title = STATE_TITLES[canonical]
        if self._mic_button is not None:
            self._mic_button.setIcon(QIcon(self._make_mic_pixmap(color)))
            # Mic is disabled while the engine cannot record. The hotkey
            # queue in WorkerThread stays active so a press during
            # reconnect still auto-starts after recovery.
            disabled = canonical in MIC_DISABLED_STATES
            self._mic_button.setEnabled(not disabled)
            self._mic_button.setToolTip(STATE_MIC_TOOLTIPS[canonical])
        if self._wave is not None:
            self._wave.set_color(color)
        if self._wave_opacity is not None:
            if canonical == "idle":
                self._wave_opacity.setOpacity(OPACITY_IDLE_WAVE_DIM)
            else:
                self._wave_opacity.setOpacity(1.0)
        if self._status_label is not None:
            if canonical == "idle" and not text:
                self._update_hint()
            elif text:
                shown = text if len(text) <= 60 else text[:57] + "..."
                self._status_label.setText(shown)
            else:
                self._status_label.setText(title)
        if self._window is not None:
            self._window.setToolTip(text if text else title)
        if canonical in PULSE_STATES:
            self._start_pulse()
        else:
            self._stop_pulse()

    def set_state(self, state: str, text: str = "") -> None:
        key = (state or "").strip().lower()
        key = STATE_ALIASES.get(key, key)
        if key not in STATE_COLORS:
            log.warning("Unknown status state %r; falling back to idle", state)
            key = "idle"
        if self._capsule is None and self._window is None:
            # Pre-show: remember state + text so first build renders correctly.
            self._state = key
            self._state_color = STATE_COLORS[key]
            self._pending_text = text
            return
        self._pending_text = text
        self._apply_state_visuals(key, text)

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


# Module-level geometry exports for toast positioning (single source —
# toast.py imports these instead of duplicating 36 + 30).
# CAPSULE_HEIGHT mirrors StatusBar.CAPSULE_HEIGHT (parity with the
# theme token is already verified in StatusBar.__init__ via log warning).
# CAPSULE_BOTTOM_MARGIN mirrors the 30px bottom offset used in
# StatusBar._move_bottom_center.
CAPSULE_HEIGHT = StatusBar.CAPSULE_HEIGHT
CAPSULE_BOTTOM_MARGIN = 30
