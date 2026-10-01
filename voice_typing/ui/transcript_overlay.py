# voice_typing/ui/transcript_overlay.py
"""Floating, always-on-top transcript overlay for real-time voice typing display."""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from voice_typing.ui._theme import (
    COLOR_FOCUS_RING,
    COLOR_OVERLAY_BG as _BG_COLOR,
    COLOR_OVERLAY_BORDER as _BORDER_COLOR,
    COLOR_OVERLAY_CARET as _CARET_COLOR,
    COLOR_OVERLAY_HOVER_BG as _HOVER_BG,
    COLOR_OVERLAY_PARTIAL_BLUE as _PARTIAL_BLUE,
    COLOR_OVERLAY_PROGRESS_BG as _PROGRESS_BG,
    COLOR_OVERLAY_PROGRESS_FILL as _PROGRESS_FILL,
    COLOR_OVERLAY_TEXT_BRIGHT as _TEXT_BRIGHT,
    COLOR_OVERLAY_TEXT_DIM as _TEXT_DIM,
    COLOR_TEXT_MUTED,
    OVERLAY_CARET_BLINK_MS as _CARET_BLINK_MS,
    OVERLAY_PROGRESS_HEIGHT as _PROGRESS_HEIGHT,
    TOUCH_TARGET_MIN,
    focus_ring_stylesheet,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_WIDTH = 450
_DEFAULT_HEIGHT = 200
_MIN_WIDTH = 300
_MIN_HEIGHT = 100
_TITLE_HEIGHT = 32
_AUTO_DISMISS_MS = 3000  # 3 seconds after recording stops
_GEOMETRY_DEBOUNCE_MS = 300
_PROGRESS_TICK_MS = 50

_FONT_FAMILY = "Segoe UI"
_DEFAULT_FONT_SIZE = 13
_DEFAULT_OPACITY = 0.92

# Segment types
PartialType = Literal["partial"]
FinalType = Literal["final"]
Segment = tuple[str, PartialType | FinalType]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class OverlaySignals(QObject):
    """Signals emitted by TranscriptOverlay (Phase C redesign)."""

    pin_toggled = Signal(bool)
    copy_clicked = Signal()
    edit_committed = Signal(str)
    geometry_changed = Signal(int, int, int, int)


# ---------------------------------------------------------------------------
# Overlay Window (internal)
# ---------------------------------------------------------------------------

class _OverlayWindow(QWidget):
    """Frameless, translucent, always-on-top overlay that displays the transcript."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        # Callbacks wired by TranscriptOverlay (avoids tight coupling).
        self.on_geometry_moved: object = None
        self.on_hover_changed: object = None

    # --- drag handling -------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._in_title_bar(event):
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            event.accept()
            cb = self.on_geometry_moved
            if callable(cb):
                cb()
            return
        super().mouseReleaseEvent(event)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        cb = self.on_geometry_moved
        if callable(cb):
            cb()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        cb = self.on_geometry_moved
        if callable(cb):
            cb()

    def enterEvent(self, event) -> None:
        cb = self.on_hover_changed
        if callable(cb):
            cb(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        cb = self.on_hover_changed
        if callable(cb):
            cb(False)
        super().leaveEvent(event)

    # --- helpers -------------------------------------------------------------

    def _in_title_bar(self, event: QMouseEvent) -> bool:
        """Return True if the click position is within the title-bar strip."""
        local_y = event.position().toPoint().y()
        return 0 <= local_y <= _TITLE_HEIGHT


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TranscriptOverlay:
    """Manages a floating transcript overlay window.

    Public API:
        show()                – display the overlay with a fade-in
        hide()                – hide the overlay with a fade-out
        add_partial(text)     – update the streaming (blue) text + blinking caret
        add_final(text)       – append finalised (bright) text
        start_auto_dismiss()  – begin a delayed hide after recording stops
        pause()               – pause the dismiss countdown (hover)
        resume()              – resume the dismiss countdown
        set_opacity(value)    – update the window opacity (0.0 – 1.0)
        set_font_size(size)   – update the text display font size
        set_pinned(pinned)    – pin the overlay (suppresses auto-dismiss)
        copy_to_clipboard()   – copy finals-only text to the system clipboard
        set_geometry_from_settings(x, y, w, h) – restore saved geometry
        close()               – immediate cleanup, destroy the window
    """

    def __init__(self) -> None:
        self.signals = OverlaySignals()
        # State
        self._segments: list[Segment] = []
        self._opacity: float = _DEFAULT_OPACITY
        self._font_size: int = _DEFAULT_FONT_SIZE
        self._enabled: bool = True
        self._max_height: int = 300
        self._auto_dismiss_seconds: float = 3.0
        self._pinned: bool = False
        self._caret_visible: bool = True
        self._pending_geometry: tuple | None = None
        # m2: suppress geometry_changed on programmatic apply (restore/
        # initial placement). While True, _schedule_geometry_emit() is a
        # no-op so only user drag/resize notifies the app.
        self._suspend_geometry_emit: bool = False

        # Window / widgets (created lazily)
        self._window: _OverlayWindow | None = None
        self._title_bar: QWidget | None = None
        self._title_label: QLabel | None = None
        self._pin_button: QPushButton | None = None
        self._copy_button: QPushButton | None = None
        self._close_button: QPushButton | None = None
        self._text_edit: QTextEdit | None = None
        self._edit_line: QLineEdit | None = None
        self._progress_bar: QProgressBar | None = None
        self._size_grip: QSizeGrip | None = None

        # Animations / timers
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._auto_dismiss_timer: QTimer | None = None
        self._caret_timer: QTimer | None = None
        self._progress_timer: QTimer | None = None
        self._progress_clock = QElapsedTimer()
        self._progress_total_ms: int = _AUTO_DISMISS_MS
        self._progress_elapsed_ms: int = 0
        self._progress_active: bool = False
        self._progress_paused: bool = False
        self._geometry_debounce: QTimer | None = None

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> _OverlayWindow:
        """Construct the overlay window, title bar, and text area."""
        win = _OverlayWindow()
        win.setWindowTitle("Transcript")
        win.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # M3 focus-steal trade-off: WA_ShowWithoutActivating keeps the overlay
        # from stealing the target app's focus on show(). The read-only
        # transcript view is NoFocus (never focusable); the edit line is
        # ClickFocus only so keyboard focus stays in the target app unless
        # the user explicitly clicks to correct text. After commit we call
        # clearFocus() to return focus. Title-bar buttons keep StrongFocus
        # for keyboard access — clicking them may briefly take focus, which
        # is accepted (user-initiated) vs. automatic steal on show/update.
        win.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        win.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        win.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        win.setMaximumHeight(self._max_height)
        win.setWindowOpacity(self._opacity)
        # Hover pause/resume + debounced geometry notifications.
        win.on_geometry_moved = self._schedule_geometry_emit
        win.on_hover_changed = self._on_hover_changed

        # --- drop shadow on the root layout wrapper -------------------------
        root_container = QWidget(win)
        root_container.setObjectName("overlayRoot")
        root_container.setStyleSheet(
            f"#overlayRoot {{ background-color: {_BG_COLOR}; "
            f"border: 1px solid {_BORDER_COLOR}; border-radius: 8px; }}"
        )
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        root_container.setGraphicsEffect(shadow)

        root_layout = QVBoxLayout(root_container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- title bar ------------------------------------------------------
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(_TITLE_HEIGHT)
        title_bar.setCursor(Qt.CursorShape.OpenHandCursor)
        title_bar.setStyleSheet(
            "#titleBar { background: transparent; border-bottom: 1px solid "
            f"{_BORDER_COLOR}; border-top-left-radius: 8px; "
            "border-top-right-radius: 8px; }"
        )
        self._title_bar = title_bar

        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 0, 8, 0)
        title_layout.setSpacing(4)

        title_label = QLabel("Transcript")
        title_label.setStyleSheet(
            f"color: {_TEXT_BRIGHT}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none; font-family: "
            f"'{_FONT_FAMILY}', sans-serif;"
        )
        self._title_label = title_label
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)

        pin_button = QPushButton("Pin")
        pin_button.setObjectName("pinBtn")
        pin_button.setCheckable(True)
        pin_button.setChecked(self._pinned)
        pin_button.setFixedSize(44, TOUCH_TARGET_MIN)
        pin_button.setCursor(Qt.CursorShape.PointingHandCursor)
        pin_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pin_button.setToolTip("Pin overlay (stay visible)")
        pin_button.setStyleSheet(
            "QPushButton {"
            f"    background: transparent; color: {COLOR_TEXT_MUTED}; border: none;"
            "    border-radius: 14px; font-size: 11px;"
            "}"
            "QPushButton:hover {"
            f"    background: {_HOVER_BG}; color: {_TEXT_BRIGHT};"
            "}"
            "QPushButton:checked {"
            f"    background: {_HOVER_BG}; color: {_PARTIAL_BLUE};"
            "}"
            + focus_ring_stylesheet(COLOR_FOCUS_RING)
        )
        self._pin_button = pin_button
        title_layout.addWidget(pin_button)

        copy_button = QPushButton("Copy")
        copy_button.setObjectName("copyBtn")
        copy_button.setFixedSize(52, TOUCH_TARGET_MIN)
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        copy_button.setToolTip("Copy final text")
        copy_button.setStyleSheet(
            "QPushButton {"
            f"    background: transparent; color: {COLOR_TEXT_MUTED}; border: none;"
            "    border-radius: 14px; font-size: 11px;"
            "}"
            "QPushButton:hover {"
            f"    background: {_HOVER_BG}; color: {_TEXT_BRIGHT};"
            "}"
            + focus_ring_stylesheet(COLOR_FOCUS_RING)
        )
        self._copy_button = copy_button
        title_layout.addWidget(copy_button)

        close_button = QPushButton("Close")
        close_button.setObjectName("closeBtn")
        close_button.setText("\u2715")
        close_button.setFixedSize(TOUCH_TARGET_MIN, TOUCH_TARGET_MIN)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        close_button.setToolTip("Close transcript")
        close_button.setStyleSheet(
            "QPushButton {"
            f"    background: transparent; color: {COLOR_TEXT_MUTED}; border: none;"
            "    border-radius: 14px; font-size: 12px; font-weight: bold;"
            "}"
            "QPushButton:hover {"
            f"    background: {_HOVER_BG}; color: {_TEXT_BRIGHT};"
            "}"
            + focus_ring_stylesheet(COLOR_FOCUS_RING)
        )
        self._close_button = close_button
        title_layout.addWidget(close_button)

        root_layout.addWidget(title_bar)

        # --- text display area -----------------------------------------------
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setObjectName("transcriptText")
        # M3: never focusable — display only, must not steal focus.
        text_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        text_edit.setFrameShape(QTextEdit.Shape.NoFrame)
        text_edit.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {_TEXT_BRIGHT}; "
            f"font-family: '{_FONT_FAMILY}', sans-serif; "
            f"font-size: {self._font_size}px; border: none; padding: 8px 12px; }}"
        )
        self._text_edit = text_edit
        root_layout.addWidget(text_edit, 1)

        # --- edit-before-inject line -----------------------------------------
        edit_line = QLineEdit()
        edit_line.setObjectName("transcriptEdit")
        edit_line.setPlaceholderText("Edit then Enter to inject...")
        edit_line.setClearButtonEnabled(True)
        # M3: click-to-focus only — no Tab-focus steal from the target app.
        edit_line.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        edit_line.setStyleSheet(
            f"QLineEdit {{ background: transparent; color: {_TEXT_BRIGHT}; "
            f"font-family: '{_FONT_FAMILY}', sans-serif; "
            f"font-size: {self._font_size}px; border-top: 1px solid {_BORDER_COLOR}; "
            "border-left: none; border-right: none; border-bottom: none; "
            "padding: 6px 12px; selection-background-color: "
            f"{_PROGRESS_FILL}; }}"
        )
        self._edit_line = edit_line
        root_layout.addWidget(edit_line)

        # --- determinate progress + resize grip ------------------------------
        bottom_row = QWidget()
        bottom_row.setObjectName("bottomRow")
        bottom_row.setStyleSheet(
            "#bottomRow { background: transparent; border: none; }"
        )
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        progress = QProgressBar()
        progress.setObjectName("dismissProgress")
        progress.setTextVisible(False)
        progress.setFixedHeight(_PROGRESS_HEIGHT)
        progress.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        progress.setMinimum(0)
        progress.setMaximum(self._progress_total_ms)
        progress.setValue(0)
        progress.setStyleSheet(
            "QProgressBar {"
            f"    background: {_PROGRESS_BG}; border: none;"
            f"    max-height: {_PROGRESS_HEIGHT}px; min-height: {_PROGRESS_HEIGHT}px;"
            "    border-bottom-left-radius: 8px;"
            "}"
            "QProgressBar::chunk {"
            f"    background: {_PROGRESS_FILL}; border: none;"
            "}"
        )
        progress.hide()
        self._progress_bar = progress
        bottom_layout.addWidget(progress, 1)

        grip = QSizeGrip(bottom_row)
        self._size_grip = grip
        bottom_layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom)

        root_layout.addWidget(bottom_row)

        # --- wire signals ----------------------------------------------------
        close_button.clicked.connect(self._on_close_clicked)
        pin_button.toggled.connect(self._on_pin_toggled)
        copy_button.clicked.connect(self._on_copy_clicked)
        edit_line.returnPressed.connect(self._on_edit_return_pressed)

        # --- timers ----------------------------------------------------------
        self._ensure_timers(win)

        # --- geometry: pending restore wins, else bottom-center --------------
        # m2: initial placement is programmatic — never emit geometry_changed.
        self._suspend_geometry_emit = True
        try:
            if self._pending_geometry is not None:
                # Temporarily lift suspension for the helper (it manages the
                # flag itself) — avoid nested-flag deadlock by releasing here.
                self._suspend_geometry_emit = False
                self._apply_pending_geometry(win)
            else:
                self._position_bottom_center(win)
        finally:
            self._suspend_geometry_emit = False
        # Drop any debounce queued during initial placement.
        try:
            if (
                self._geometry_debounce is not None
                and self._geometry_debounce.isActive()
            ):
                self._geometry_debounce.stop()
        except Exception:
            pass
        self._render_segments()
        self._update_progress_visibility()
        return win

    def _ensure_timers(self, parent: QWidget) -> None:
        """Create caret / progress / debounce timers lazily (needs a parent)."""
        if self._caret_timer is None:
            self._caret_timer = QTimer(parent)
            self._caret_timer.setInterval(_CARET_BLINK_MS)
            self._caret_timer.timeout.connect(self._on_caret_blink)
        if self._progress_timer is None:
            self._progress_timer = QTimer(parent)
            self._progress_timer.setInterval(_PROGRESS_TICK_MS)
            self._progress_timer.timeout.connect(self._on_progress_tick)
        if self._geometry_debounce is None:
            self._geometry_debounce = QTimer(parent)
            self._geometry_debounce.setSingleShot(True)
            self._geometry_debounce.setInterval(_GEOMETRY_DEBOUNCE_MS)
            self._geometry_debounce.timeout.connect(self._emit_geometry_changed)
        if self._auto_dismiss_timer is None:
            self._auto_dismiss_timer = QTimer(parent)
            self._auto_dismiss_timer.setSingleShot(True)
            self._auto_dismiss_timer.timeout.connect(self._on_auto_dismiss_timeout)

    def _apply_pending_geometry(self, win: QWidget) -> None:
        pending = self._pending_geometry
        if pending is None:
            return
        x, y, w, h = pending
        if isinstance(w, int) and isinstance(h, int):
            w = max(_MIN_WIDTH, w)
            h = max(_MIN_HEIGHT, min(600, h))
        # m1 (defense-in-depth): clamp x/y to the available screen here as
        # well — app._restore_overlay_geometry() already clamps, but the
        # overlay must stay on-screen even if called directly.
        if isinstance(x, int) and isinstance(y, int):
            try:
                screen = QApplication.primaryScreen()
                if screen is not None:
                    avail = screen.availableGeometry()
                    x = max(avail.x(), min(x, avail.x() + avail.width() - 100))
                    y = max(avail.y(), min(y, avail.y() + avail.height() - 50))
            except Exception:
                pass
        # m2: programmatic move/resize must not emit geometry_changed.
        self._suspend_geometry_emit = True
        try:
            if isinstance(w, int) and isinstance(h, int):
                win.resize(w, h)
            if isinstance(x, int) and isinstance(y, int):
                win.move(x, y)
            else:
                self._position_bottom_center(win)
        finally:
            self._suspend_geometry_emit = False
        # Drop any debounce queued during the programmatic move.
        try:
            if (
                self._geometry_debounce is not None
                and self._geometry_debounce.isActive()
            ):
                self._geometry_debounce.stop()
        except Exception:
            pass

    def _position_bottom_center(self, win: QWidget) -> None:
        """Centre the overlay horizontally near the bottom of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = (geo.width() - win.width()) // 2 + geo.x()
        y = geo.height() - win.height() - 30 + geo.y()
        win.move(x, y)

    # ------------------------------------------------------------------
    # Text rendering
    # ------------------------------------------------------------------

    def _render_segments(self) -> None:
        """Rebuild the QTextEdit contents from the current segment list."""
        if self._text_edit is None:
            return
        from PySide6.QtGui import QTextCursor as _Cursor

        cursor = self._text_edit.textCursor()
        cursor.select(_Cursor.SelectionType.Document)
        cursor.removeSelectedText()

        html_parts: list[str] = []
        for text, kind in self._segments:
            escaped = (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            if kind == "partial":
                html_parts.append(
                    f'<span style="color: {_PARTIAL_BLUE};">{escaped}</span>'
                )
            else:
                html_parts.append(
                    f'<span style="color: {_TEXT_BRIGHT};">{escaped}</span>'
                )
        # Blinking caret follows the live partial (Phase C).
        if (
            self._segments
            and self._segments[-1][1] == "partial"
            and self._caret_visible
        ):
            html_parts.append(
                f'<span style="color: {_CARET_COLOR};">\u258d</span>'
            )

        self._text_edit.setHtml("".join(html_parts))

        # Auto-scroll to the bottom
        sb = self._text_edit.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    # ------------------------------------------------------------------
    # Animations
    # ------------------------------------------------------------------

    def _cancel_fade_in(self) -> None:
        """Cancel any in-progress fade-in animation."""
        if self._fade_in_anim is not None:
            anim, self._fade_in_anim = self._fade_in_anim, None
            anim.stop()
            anim.deleteLater()

    def _cancel_fade_out(self) -> None:
        """Cancel any in-progress fade-out animation."""
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.stop()
            anim.deleteLater()

    def _on_fade_in_finished(self) -> None:
        """Clean up the fade-in animation once it completes."""
        if self._fade_in_anim is not None:
            anim, self._fade_in_anim = self._fade_in_anim, None
            anim.deleteLater()
        # Ensure the stored opacity is applied
        if self._window is not None:
            self._window.setWindowOpacity(self._opacity)

    def _on_fade_out_finished(self) -> None:
        """Hide the window once the fade-out completes."""
        if self._fade_out_anim is not None:
            anim, self._fade_out_anim = self._fade_out_anim, None
            anim.deleteLater()
        if self._window is not None:
            self._window.hide()
        self._stop_progress()
        # M2: caret must not leak past hide — stop blink timer here (hide()
        # also stops it for the fade window; this covers completion).
        self._stop_caret_timer()

    # ------------------------------------------------------------------
    # Auto-dismiss + determinate progress
    # ------------------------------------------------------------------

    def _on_auto_dismiss_timeout(self) -> None:
        """Called when the auto-dismiss timer fires."""
        self._progress_active = False
        self._update_progress_visibility()
        self.hide()

    def _start_progress(self) -> None:
        """Start the determinate dismiss countdown (50ms tick + elapsed clock)."""
        total = int(self._auto_dismiss_seconds * 1000)
        self._progress_total_ms = max(1000, total)
        self._progress_elapsed_ms = 0
        self._progress_active = True
        self._progress_paused = False
        self._progress_clock.start()
        if self._progress_bar is not None:
            self._progress_bar.setMaximum(self._progress_total_ms)
            self._progress_bar.setValue(0)
        if self._progress_timer is not None and not self._progress_timer.isActive():
            self._progress_timer.start()
        self._update_progress_visibility()

    def _stop_progress(self) -> None:
        """Stop the progress countdown and hide the bar."""
        self._progress_active = False
        self._progress_paused = False
        self._progress_elapsed_ms = 0
        if self._progress_timer is not None and self._progress_timer.isActive():
            self._progress_timer.stop()
        self._update_progress_visibility()

    def _on_progress_tick(self) -> None:
        """Advance the determinate bar from the elapsed clock (50ms tick)."""
        if not self._progress_active or self._progress_paused:
            return
        elapsed = self._progress_elapsed_ms
        if self._progress_clock.isValid():
            elapsed += int(self._progress_clock.elapsed())
        elapsed = min(elapsed, self._progress_total_ms)
        if self._progress_bar is not None:
            self._progress_bar.setValue(elapsed)

    def _update_progress_visibility(self) -> None:
        """The 3px bar is visible only during an unpinned countdown."""
        if self._progress_bar is None:
            return
        if self._pinned or not self._progress_active:
            self._progress_bar.hide()
        else:
            self._progress_bar.show()

    def _on_hover_changed(self, hovered: bool) -> None:
        """Hover pauses the countdown; leaving resumes it."""
        if not self._progress_active or self._pinned:
            return
        if hovered:
            self.pause()
        else:
            self.resume()

    # ------------------------------------------------------------------
    # Caret blink
    # ------------------------------------------------------------------

    def _on_caret_blink(self) -> None:
        """Toggle the live-partial caret and re-render."""
        if self._window is None:
            return
        if not self._segments or self._segments[-1][1] != "partial":
            # M2: no live partial — stop the timer instead of idling.
            self._stop_caret_timer()
            return
        self._caret_visible = not self._caret_visible
        self._render_segments()

    def _ensure_caret_running(self) -> None:
        if self._caret_timer is not None and not self._caret_timer.isActive():
            self._caret_timer.start()

    def _stop_caret_timer(self) -> None:
        """Stop the caret blink timer if running (M2 leak fix)."""
        try:
            if self._caret_timer is not None and self._caret_timer.isActive():
                self._caret_timer.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Geometry debounce
    # ------------------------------------------------------------------

    def _schedule_geometry_emit(self) -> None:
        """Restart the debounced geometry_changed emission."""
        # m2: ignore programmatic applies (restore/initial placement).
        if self._suspend_geometry_emit:
            return
        if self._geometry_debounce is not None:
            self._geometry_debounce.start()

    def _emit_geometry_changed(self) -> None:
        """Emit the current window geometry after move/resize settles."""
        if self._window is None:
            return
        geo = self._window.geometry()
        self.signals.geometry_changed.emit(geo.x(), geo.y(), geo.width(), geo.height())

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_close_clicked(self) -> None:
        """Handle the title-bar close button click."""
        self.hide()

    def _on_pin_toggled(self, checked: bool) -> None:
        """Handle the pin button toggle (suppresses auto-dismiss)."""
        self._pinned = bool(checked)
        if self._pinned:
            self._cancel_auto_dismiss()
            self._stop_progress()
        else:
            self._update_progress_visibility()
        self.signals.pin_toggled.emit(self._pinned)

    def _on_copy_clicked(self) -> None:
        """Handle the copy button click (finals-only)."""
        self.copy_to_clipboard()
        self.signals.copy_clicked.emit()

    def _on_edit_return_pressed(self) -> None:
        """Commit the edit line: replace finals, then notify the app to inject."""
        if self._edit_line is None:
            return
        text = self._edit_line.text().strip()
        if not text:
            return
        # Edit replaces finals (single committed final, stale partial dropped).
        if self._segments and self._segments[-1][1] == "partial":
            self._segments.pop()
        self._segments = [(text, "final")]
        self._render_segments()
        self._edit_line.clear()
        # M3: return focus to the target app after commit.
        try:
            self._edit_line.clearFocus()
        except Exception:
            pass
        # No trailing partial remains — stop the caret (M2).
        self._stop_caret_timer()
        self.signals.edit_committed.emit(text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Display the overlay with a fade-in animation."""
        if not self._enabled:
            return
        if self._window is None:
            self._window = self._build_window()
            self._window.setWindowOpacity(0.0)
        else:
            self._ensure_timers(self._window)

        # Stop any pending auto-dismiss
        self._cancel_auto_dismiss()
        self._stop_progress()

        self._cancel_fade_out()
        self._cancel_fade_in()
        self._window.show()
        self._window.raise_()
        self._ensure_caret_running()

        if self._window.windowOpacity() < self._opacity:
            anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
            anim.setDuration(150)
            anim.setStartValue(self._window.windowOpacity())
            anim.setEndValue(self._opacity)
            anim.finished.connect(self._on_fade_in_finished)
            self._fade_in_anim = anim
            anim.start()

    def hide(self) -> None:
        """Hide the overlay with a fade-out animation."""
        self._cancel_auto_dismiss()
        self._stop_progress()
        # M2: stop caret blink on hide so the timer never leaks while hidden.
        self._stop_caret_timer()
        if self._window is None:
            return
        if self._fade_out_anim is not None:
            return  # already fading out
        self._cancel_fade_in()

        anim = QPropertyAnimation(self._window, b"windowOpacity", self._window)
        anim.setDuration(120)
        anim.setStartValue(self._window.windowOpacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self._on_fade_out_finished)
        self._fade_out_anim = anim
        anim.start()

    def add_partial(self, text: str) -> None:
        """Update the streaming (blue) text with a blinking caret.

        If the last segment is already partial it is replaced; otherwise a new
        partial segment is appended.
        """
        if not self._enabled or not text:
            return
        if self._segments and self._segments[-1][1] == "partial":
            self._segments[-1] = (text, "partial")
        else:
            self._segments.append((text, "partial"))
        self._caret_visible = True
        self._ensure_caret_running()
        self._render_segments()

    def add_final(self, text: str) -> None:
        """Append finalised (bright) text and clear any pending partial.

        The most recent partial segment is removed before appending the final
        text so that the final result appears clean.
        """
        # M1: same _enabled guard as add_partial (previously missing).
        if not self._enabled or not text:
            return
        # Remove trailing partial – it will be superseded by the final text
        if self._segments and self._segments[-1][1] == "partial":
            self._segments.pop()
        self._segments.append((text, "final"))
        self._render_segments()
        # M2: no trailing partial remains after a final — stop the caret
        # blink timer so it never leaks while only finals are shown.
        self._stop_caret_timer()

    def start_auto_dismiss(self) -> None:
        """Begin the delayed-hide timer after recording stops."""
        if not self._enabled:
            return
        if self._pinned:
            return  # pinned overlays never auto-dismiss
        if self._auto_dismiss_timer is None:
            if self._window is not None:
                self._ensure_timers(self._window)
            else:
                return
        total_ms = int(self._auto_dismiss_seconds * 1000)
        self._auto_dismiss_timer.start(total_ms)
        self._start_progress()

    def pause(self) -> None:
        """Pause the dismiss countdown (hover). Safe to call when idle."""
        if not self._progress_active or self._progress_paused:
            return
        if self._progress_clock.isValid():
            self._progress_elapsed_ms += int(self._progress_clock.elapsed())
        if self._auto_dismiss_timer is not None and self._auto_dismiss_timer.isActive():
            remaining = self._auto_dismiss_timer.remainingTime()
            self._auto_dismiss_timer.stop()
            self._progress_elapsed_ms = max(
                0, self._progress_total_ms - max(0, remaining)
            )
        self._progress_paused = True
        if self._progress_timer is not None and self._progress_timer.isActive():
            self._progress_timer.stop()

    def resume(self) -> None:
        """Resume a paused dismiss countdown. Safe to call when idle."""
        if not self._progress_active or not self._progress_paused:
            return
        remaining = max(0, self._progress_total_ms - self._progress_elapsed_ms)
        if self._auto_dismiss_timer is not None:
            self._auto_dismiss_timer.start(max(1, remaining))
        self._progress_clock.start()
        self._progress_paused = False
        if self._progress_timer is not None and not self._progress_timer.isActive():
            self._progress_timer.start()

    def set_pinned(self, pinned: bool) -> None:
        """Pin or unpin the overlay. Pinned overlays suppress auto-dismiss."""
        pinned = bool(pinned)
        if self._pinned == pinned:
            if self._pin_button is not None and self._pin_button.isChecked() != pinned:
                self._pin_button.blockSignals(True)
                try:
                    self._pin_button.setChecked(pinned)
                finally:
                    self._pin_button.blockSignals(False)
            return
        self._pinned = pinned
        if self._pin_button is not None:
            self._pin_button.blockSignals(True)
            try:
                self._pin_button.setChecked(pinned)
            finally:
                self._pin_button.blockSignals(False)
        if pinned:
            self._cancel_auto_dismiss()
            self._stop_progress()
        else:
            self._update_progress_visibility()
        self.signals.pin_toggled.emit(self._pinned)

    @property
    def is_pinned(self) -> bool:
        """Return whether the overlay is currently pinned."""
        return self._pinned

    def copy_to_clipboard(self) -> str:
        """Copy finals-only text to the system clipboard. Returns the text."""
        finals = [text for text, kind in self._segments if kind == "final"]
        joined = " ".join(finals).strip()
        if joined:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(joined)
        return joined

    def set_geometry_from_settings(
        self,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        """Restore saved geometry. Applies immediately or defers until show()."""
        w = width if isinstance(width, int) else _DEFAULT_WIDTH
        h = height if isinstance(height, int) else _DEFAULT_HEIGHT
        w = max(_MIN_WIDTH, w)
        h = max(_MIN_HEIGHT, min(600, h))
        if not isinstance(x, int) or not isinstance(y, int):
            x, y = None, None
        self._pending_geometry = (x, y, w, h)
        if self._window is not None:
            self._apply_pending_geometry(self._window)

    def set_opacity(self, value: float) -> None:
        """Update the window opacity (clamped to 0.5 – 1.0)."""
        self._opacity = max(0.5, min(1.0, value))
        if self._window is not None:
            self._window.setWindowOpacity(self._opacity)

    def set_font_size(self, size: int) -> None:
        """Update the font size of the transcript text display."""
        self._font_size = max(8, min(36, size))
        if self._text_edit is not None:
            # Qt stylesheets override setFont(), so we must re-apply the
            # stylesheet with the updated font-size in pixels.
            self._text_edit.setStyleSheet(
                f"QTextEdit {{ background: transparent; color: {_TEXT_BRIGHT}; "
                f"font-family: '{_FONT_FAMILY}', sans-serif; "
                f"font-size: {self._font_size}px; border: none; padding: 8px 12px; }}"
            )
            # Re-render so styled spans pick up the new size
            self._render_segments()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the overlay. When disabled, show()/add_partial() are no-ops."""
        self._enabled = enabled
        if not enabled:
            self.close()

    @property
    def is_enabled(self) -> bool:
        """Return whether the overlay is currently enabled."""
        return self._enabled

    def set_max_height(self, height: int) -> None:
        """Update the maximum height of the overlay window."""
        self._max_height = max(100, min(600, height))
        if self._window is not None:
            self._window.setMaximumHeight(self._max_height)

    def set_auto_dismiss_seconds(self, seconds: float) -> None:
        """Set the delay (in seconds) before the overlay auto-hides after recording stops."""
        self._auto_dismiss_seconds = max(1.0, min(30.0, seconds))

    def close(self) -> None:
        """Immediate cleanup – destroy the window without animation."""
        self._cancel_auto_dismiss()
        self._cancel_fade_in()
        self._cancel_fade_out()
        self._stop_progress()
        if self._caret_timer is not None and self._caret_timer.isActive():
            self._caret_timer.stop()
        if self._geometry_debounce is not None and self._geometry_debounce.isActive():
            self._geometry_debounce.stop()
        if self._window is not None:
            self._window.hide()
            self._window.deleteLater()
            self._window = None
            self._title_bar = None
            self._title_label = None
            self._pin_button = None
            self._copy_button = None
            self._close_button = None
            self._text_edit = None
            self._edit_line = None
            self._progress_bar = None
            self._size_grip = None
        self._caret_timer = None
        self._progress_timer = None
        self._geometry_debounce = None
        self._auto_dismiss_timer = None
        self._segments.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cancel_auto_dismiss(self) -> None:
        """Stop the auto-dismiss timer if it is running."""
        if self._auto_dismiss_timer is not None and self._auto_dismiss_timer.isActive():
            self._auto_dismiss_timer.stop()
