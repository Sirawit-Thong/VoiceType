# voice_typing/ui/transcript_overlay.py
"""Floating, always-on-top transcript overlay for real-time voice typing display."""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import (
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
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

# Theme colours (shared with status_bar / _theme)
_BG_COLOR = "#1a1b1e"
_BORDER_COLOR = "#3c4043"
_TEXT_BRIGHT = "#e8eaed"
_TEXT_DIM = "#888888"
_HOVER_BG = "rgba(255, 255, 255, 0.08)"

_FONT_FAMILY = "Segoe UI"
_DEFAULT_FONT_SIZE = 13
_DEFAULT_OPACITY = 0.92

# Segment types
PartialType = Literal["partial"]
FinalType = Literal["final"]
Segment = tuple[str, PartialType | FinalType]


# ---------------------------------------------------------------------------
# Overlay Window (internal)
# ---------------------------------------------------------------------------

class _OverlayWindow(QWidget):
    """Frameless, translucent, always-on-top overlay that displays the transcript."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None

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
            return
        super().mouseReleaseEvent(event)

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
        add_partial(text)     – update the streaming (dimmed) text
        add_final(text)       – append finalised (bright) text
        start_auto_dismiss()  – begin a delayed hide after recording stops
        set_opacity(value)    – update the window opacity (0.0 – 1.0)
        set_font_size(size)   – update the text display font size
        close()               – immediate cleanup, destroy the window
    """

    def __init__(self) -> None:
        # State
        self._segments: list[Segment] = []
        self._opacity: float = _DEFAULT_OPACITY
        self._font_size: int = _DEFAULT_FONT_SIZE
        self._enabled: bool = True
        self._max_height: int = 300
        self._auto_dismiss_seconds: float = 3.0

        # Window / widgets (created lazily)
        self._window: _OverlayWindow | None = None
        self._title_bar: QWidget | None = None
        self._title_label: QLabel | None = None
        self._close_button: QPushButton | None = None
        self._text_edit: QTextEdit | None = None

        # Animations / timers
        self._fade_in_anim: QPropertyAnimation | None = None
        self._fade_out_anim: QPropertyAnimation | None = None
        self._auto_dismiss_timer: QTimer | None = None

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
        )
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        win.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
        win.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        win.setMaximumHeight(self._max_height)
        win.setWindowOpacity(self._opacity)

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
        title_layout.setSpacing(0)

        title_label = QLabel("Transcript")
        title_label.setStyleSheet(
            f"color: {_TEXT_BRIGHT}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none; font-family: "
            f"'{_FONT_FAMILY}', sans-serif;"
        )
        self._title_label = title_label
        title_layout.addWidget(title_label)
        title_layout.addStretch(1)

        close_button = QPushButton("✕")
        close_button.setObjectName("closeBtn")
        close_button.setFixedSize(20, 20)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setToolTip("Close transcript")
        close_button.setStyleSheet(
            "QPushButton {"
            "    background: transparent; color: #9aa0a6; border: none;"
            "    border-radius: 10px; font-size: 12px; font-weight: bold;"
            "}"
            "QPushButton:hover {"
            f"    background: {_HOVER_BG}; color: {_TEXT_BRIGHT};"
            "}"
        )
        self._close_button = close_button
        title_layout.addWidget(close_button)

        root_layout.addWidget(title_bar)

        # --- text display area -----------------------------------------------
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setObjectName("transcriptText")
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

        # --- wire signals ----------------------------------------------------
        close_button.clicked.connect(self._on_close_clicked)

        # --- position the window at bottom-center ---------------------------
        self._position_bottom_center(win)

        return win

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
        cursor = self._text_edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
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
                    f'<span style="color: {_TEXT_DIM};">{escaped}</span>'
                )
            else:
                html_parts.append(
                    f'<span style="color: {_TEXT_BRIGHT};">{escaped}</span>'
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

    # ------------------------------------------------------------------
    # Auto-dismiss
    # ------------------------------------------------------------------

    def _on_auto_dismiss_timeout(self) -> None:
        """Called when the auto-dismiss timer fires."""
        self.hide()

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_close_clicked(self) -> None:
        """Handle the title-bar close button click."""
        self.hide()

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

        # Stop any pending auto-dismiss
        self._cancel_auto_dismiss()

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

    def hide(self) -> None:
        """Hide the overlay with a fade-out animation."""
        self._cancel_auto_dismiss()
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
        """Update the streaming (partial) text.

        If the last segment is already partial it is replaced; otherwise a new
        partial segment is appended.
        """
        if not self._enabled or not text:
            return
        if self._segments and self._segments[-1][1] == "partial":
            self._segments[-1] = (text, "partial")
        else:
            self._segments.append((text, "partial"))
        self._render_segments()

    def add_final(self, text: str) -> None:
        """Append finalised (bright) text and clear any pending partial.

        The most recent partial segment is removed before appending the final
        text so that the final result appears clean.
        """
        # Remove trailing partial – it will be superseded by the final text
        if self._segments and self._segments[-1][1] == "partial":
            self._segments.pop()
        self._segments.append((text, "final"))
        self._render_segments()

    def start_auto_dismiss(self) -> None:
        """Begin the delayed-hide timer after recording stops."""
        if not self._enabled:
            return
        if self._auto_dismiss_timer is None:
            self._auto_dismiss_timer = QTimer()
            self._auto_dismiss_timer.setSingleShot(True)
            self._auto_dismiss_timer.timeout.connect(self._on_auto_dismiss_timeout)
        self._auto_dismiss_timer.start(int(self._auto_dismiss_seconds * 1000))

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
        if self._window is not None:
            self._window.hide()
            self._window.deleteLater()
            self._window = None
            self._title_bar = None
            self._title_label = None
            self._close_button = None
            self._text_edit = None
        self._segments.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cancel_auto_dismiss(self) -> None:
        """Stop the auto-dismiss timer if it is running."""
        if self._auto_dismiss_timer is not None and self._auto_dismiss_timer.isActive():
            self._auto_dismiss_timer.stop()
