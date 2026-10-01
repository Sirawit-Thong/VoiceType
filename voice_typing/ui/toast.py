# voice_typing/ui/toast.py
"""UX Phase B: bottom-center toast notifications (transient + persistent).

Single-instance ToastManager owned by VoiceTypeApp:

- show_transient(msg): auto-dismissing notice (default 3000ms), yellow accent.
- show_persistent(msg): sticky error with "Open Settings" + "Dismiss"
  buttons, red accent. Replaces any transient.
- A transient never clobbers a persistent (ignored while persistent shows).
- The window never steals focus: ToolTip | StaysOnTop | Frameless window
  flags plus WA_ShowWithoutActivating and WA_TranslucentBackground.
- Positioned bottom-center *above* the capsule/status-bar strip so the
  toast and capsule never overlap.

Dismiss policy (decided Phase B):
  transient  → auto-dismiss timer only.
  persistent → dismissed by Reconnected status, user Dismiss click, or the
               next successful recording start (VoiceTypeApp routes all
               three to hide()).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from voice_typing.ui._theme import (
    COLOR_TOAST_PERSISTENT_ACCENT,
    COLOR_TOAST_TRANSIENT_ACCENT,
    TOAST_FADE_IN_MS,
    TOAST_FADE_OUT_MS,
    TOAST_OPACITY,
    TOAST_TRANSIENT_MS,
    toast_stylesheet,
)
from voice_typing.ui.status_bar import CAPSULE_BOTTOM_MARGIN, CAPSULE_HEIGHT

log = logging.getLogger(__name__)

# Gap between the capsule strip and the toast, in pixels.
_TOAST_CAPSULE_GAP = 12
# Capsule strip footprint shared from status_bar (capsule height + bottom
# margin) so the toast never overlaps the capsule; do not hardcode 36+30.
_TOAST_CAPSULE_FOOTPRINT = CAPSULE_HEIGHT + CAPSULE_BOTTOM_MARGIN
_TOAST_MAX_WIDTH = 420


class ToastSignals(QObject):
    open_settings = Signal()


class ToastManager:
    """Owns one toast window; transient and persistent share the instance."""

    def __init__(self) -> None:
        self.signals = ToastSignals()
        self._window: QWidget | None = None
        self._root: QWidget | None = None
        self._label: QLabel | None = None
        self._buttons_row: QWidget | None = None
        self._mode: str | None = None  # "transient" | "persistent" | None
        self._message: str = ""
        self._dismiss_timer: QTimer | None = None
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str | None:
        """Current toast mode ("transient" | "persistent" | None)."""
        return self._mode

    @property
    def message(self) -> str:
        """Currently displayed message ("" when hidden)."""
        return self._message if self._mode is not None else ""

    def is_showing(self) -> bool:
        return self._mode is not None

    def show_transient(self, msg: str, duration_ms: int = TOAST_TRANSIENT_MS) -> None:
        """Show an auto-dismissing notice.

        Ignored while a persistent toast is showing (a transient must never
        clobber a sticky error).
        """
        if self._mode == "persistent":
            log.debug("Transient toast suppressed (persistent showing)")
            return
        if not msg:
            return
        self._show("transient", msg, COLOR_TOAST_TRANSIENT_ACCENT)
        self._restart_dismiss_timer(duration_ms)

    def show_persistent(self, msg: str) -> None:
        """Show a sticky error with Open Settings + Dismiss actions.

        Replaces any transient currently showing.
        """
        if not msg:
            return
        self._stop_dismiss_timer()
        self._show("persistent", msg, COLOR_TOAST_PERSISTENT_ACCENT)

    def hide(self) -> None:
        """Dismiss the toast (transient or persistent)."""
        # Clear logical state synchronously so routing decisions
        # (e.g. "transient never clobbers persistent") take effect
        # immediately even while the fade-out animation still runs.
        self._stop_dismiss_timer()
        self._mode = None
        self._message = ""
        if self._window is None:
            return
        if self._fade_out_anim is not None:
            return  # already fading out
        self._cancel_fade_in()
        anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
        anim.setDuration(TOAST_FADE_OUT_MS)
        anim.setStartValue(self._window.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._on_fade_out_finished)
        self._fade_out_anim = anim
        anim.start()

    def close(self) -> None:
        """Immediate cleanup — destroy the window."""
        self._stop_dismiss_timer()
        self._cancel_fade_in()
        self._cancel_fade_out()
        self._mode = None
        self._message = ""
        if self._window is not None:
            self._window.hide()
            self._window.deleteLater()
            self._window = None
            self._root = None
            self._label = None
            self._buttons_row = None

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> QWidget:
        win = QWidget()
        win.setWindowTitle("VoiceType")
        # Never steal focus: ToolTip windows don't take activation, and
        # WA_ShowWithoutActivating guarantees show() won't activate either.
        win.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        win.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        win.setWindowOpacity(0.0)

        root = QWidget(win)
        root.setObjectName("toastRoot")
        self._root = root

        outer = QVBoxLayout(win)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        row = QHBoxLayout(root)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)

        label = QLabel()
        label.setObjectName("toastMsg")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setMaximumWidth(_TOAST_MAX_WIDTH)
        self._label = label
        row.addWidget(label, 1)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(4)

        open_btn = QPushButton("Open Settings")
        open_btn.setObjectName("toastBtn")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        open_btn.clicked.connect(self._on_open_settings_clicked)
        buttons_layout.addWidget(open_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setObjectName("toastBtn")
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        dismiss_btn.clicked.connect(self.hide)
        buttons_layout.addWidget(dismiss_btn)

        self._buttons_row = buttons
        row.addWidget(buttons)
        return win

    def _show(self, mode: str, msg: str, accent: str) -> None:
        if self._window is None:
            self._window = self._build_window()
            self._window.setWindowOpacity(0.0)
        if (
            self._label is None
            or self._buttons_row is None
            or self._root is None
            or self._window is None
        ):
            log.warning("Toast window incomplete; skipping show (%s)", mode)
            return
        self._cancel_fade_out()
        self._cancel_fade_in()
        self._mode = mode
        # Plain text (never rich text): status/error strings must not be
        # interpreted as HTML.
        self._message = msg
        self._label.setText(msg)
        self._buttons_row.setVisible(mode == "persistent")
        self._root.setStyleSheet(toast_stylesheet(accent))
        self._window.adjustSize()
        self._position_above_capsule()
        self._window.show()
        # Masked logging: statuses carry only masked key suffixes
        # (KeyPool.mask); still cap length, never log raw key material.
        log.debug("Toast %s: %r", mode, msg[:120])
        if self._window.windowOpacity() < TOAST_OPACITY:
            anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
            anim.setDuration(TOAST_FADE_IN_MS)
            anim.setStartValue(self._window.windowOpacity())
            anim.setEndValue(TOAST_OPACITY)
            anim.finished.connect(self._on_fade_in_finished)
            self._fade_in_anim = anim
            anim.start()
        else:
            self._window.setWindowOpacity(TOAST_OPACITY)

    def _position_above_capsule(self) -> None:
        """Center horizontally near the bottom, above the capsule strip."""
        if self._window is None:
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = self._window.width() or self._window.sizeHint().width()
        h = self._window.height() or self._window.sizeHint().height()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + geo.height() - _TOAST_CAPSULE_FOOTPRINT - _TOAST_CAPSULE_GAP - h
        self._window.move(x, y)

    # ------------------------------------------------------------------
    # Handlers / timers / animations
    # ------------------------------------------------------------------

    def _on_open_settings_clicked(self) -> None:
        self.signals.open_settings.emit()

    def _on_dismiss_timeout(self) -> None:
        self.hide()

    def _restart_dismiss_timer(self, duration_ms: int) -> None:
        if self._dismiss_timer is None:
            self._dismiss_timer = QTimer()
            self._dismiss_timer.setSingleShot(True)
            self._dismiss_timer.timeout.connect(self._on_dismiss_timeout)
        self._dismiss_timer.start(max(0, duration_ms))

    def _stop_dismiss_timer(self) -> None:
        if self._dismiss_timer is not None and self._dismiss_timer.isActive():
            self._dismiss_timer.stop()

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
        if self._window is not None:
            self._window.setWindowOpacity(TOAST_OPACITY)

    def _on_fade_out_finished(self) -> None:
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.deleteLater()
        if self._mode is not None:
            # A new toast was shown during fade-out; keep it visible
            # instead of hiding the fresh window.
            return
        if self._window is not None:
            self._window.hide()
