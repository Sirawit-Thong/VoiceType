# tests/test_transcript_overlay.py
import os

# Must be set before PySide6 is imported so widgets can run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voice_typing.ui.transcript_overlay import (
    TranscriptOverlay,
    _OverlayWindow,
    _DEFAULT_FONT_SIZE,
    _DEFAULT_OPACITY,
    _DEFAULT_WIDTH,
    _DEFAULT_HEIGHT,
    _MIN_WIDTH,
    _MIN_HEIGHT,
    _FONT_FAMILY,
    _TEXT_BRIGHT,
    _TEXT_DIM,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication exists for the module (offscreen)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def overlay(qapp):
    """Create a fresh TranscriptOverlay and tear it down after each test."""
    ov = TranscriptOverlay()
    yield ov
    ov.close()
    QApplication.processEvents()


@pytest.fixture
def visible_overlay(qapp, overlay):
    """Create a TranscriptOverlay and ensure its window is built and visible."""
    overlay.show()
    QTest.qWait(50)
    QApplication.processEvents()
    return overlay


# ---------------------------------------------------------------------------
# Import & basic structure
# ---------------------------------------------------------------------------

class TestImports:
    def test_import_constants_exist(self):
        assert isinstance(_DEFAULT_FONT_SIZE, int)
        assert isinstance(_DEFAULT_OPACITY, float)
        assert isinstance(_DEFAULT_WIDTH, int)
        assert isinstance(_DEFAULT_HEIGHT, int)
        assert isinstance(_MIN_WIDTH, int)
        assert isinstance(_MIN_HEIGHT, int)
        assert isinstance(_FONT_FAMILY, str)
        assert isinstance(_TEXT_BRIGHT, str)
        assert isinstance(_TEXT_DIM, str)

    def test_import_overlay_class_exists(self):
        assert hasattr(TranscriptOverlay, "show")
        assert hasattr(TranscriptOverlay, "hide")
        assert hasattr(TranscriptOverlay, "add_partial")
        assert hasattr(TranscriptOverlay, "add_final")
        assert hasattr(TranscriptOverlay, "set_opacity")
        assert hasattr(TranscriptOverlay, "set_font_size")
        assert hasattr(TranscriptOverlay, "set_enabled")
        assert hasattr(TranscriptOverlay, "set_max_height")
        assert hasattr(TranscriptOverlay, "set_auto_dismiss_seconds")
        assert hasattr(TranscriptOverlay, "close")

    def test_import_overlay_window_class(self):
        from PySide6.QtWidgets import QWidget
        assert issubclass(_OverlayWindow, QWidget)
        assert hasattr(_OverlayWindow, "mousePressEvent")


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

class TestDefaultState:
    def test_segments_empty(self, overlay):
        assert overlay._segments == []

    def test_opacity_default(self, overlay):
        assert overlay._opacity == _DEFAULT_OPACITY

    def test_font_size_default(self, overlay):
        assert overlay._font_size == _DEFAULT_FONT_SIZE

    def test_enabled_default(self, overlay):
        assert overlay._enabled is True

    def test_max_height_default(self, overlay):
        assert overlay._max_height == 300

    def test_auto_dismiss_seconds_default(self, overlay):
        assert overlay._auto_dismiss_seconds == 3.0

    def test_window_not_created_initially(self, overlay):
        assert overlay._window is None

    def test_text_edit_not_created_initially(self, overlay):
        assert overlay._text_edit is None

    def test_is_enabled_property(self, overlay):
        assert overlay.is_enabled is True


# ---------------------------------------------------------------------------
# add_partial() behavior
# ---------------------------------------------------------------------------

class TestAddPartial:
    def test_add_partial_creates_segment(self, overlay):
        overlay.add_partial("Hello")
        assert len(overlay._segments) == 1
        assert overlay._segments[0] == ("Hello", "partial")

    def test_add_partial_replaces_trailing_partial(self, overlay):
        overlay.add_partial("Hel")
        overlay.add_partial("Hello")
        assert len(overlay._segments) == 1
        assert overlay._segments[0] == ("Hello", "partial")

    def test_add_partial_after_final_keeps_final(self, overlay):
        overlay.add_final("Done")
        overlay.add_partial("New")
        assert len(overlay._segments) == 2
        assert overlay._segments[0] == ("Done", "final")
        assert overlay._segments[1] == ("New", "partial")

    def test_add_partial_empty_string_ignored(self, overlay):
        overlay.add_partial("")
        assert overlay._segments == []

    def test_add_partial_whitespace_accepted(self, overlay):
        overlay.add_partial(" ")
        assert len(overlay._segments) == 1

    def test_add_partial_renders_to_text_edit(self, visible_overlay):
        visible_overlay.add_partial("Streaming text")
        assert visible_overlay._text_edit is not None
        html = visible_overlay._text_edit.toHtml()
        assert "Streaming text" in html

    def test_add_partial_dim_color_in_rendered_html(self, visible_overlay):
        # UX Phase C: partial renders in overlay blue, not legacy dim gray.
        from voice_typing.ui import _theme as theme

        visible_overlay.add_partial("dim text")
        html = visible_overlay._text_edit.toHtml()
        assert theme.COLOR_OVERLAY_PARTIAL_BLUE in html


# ---------------------------------------------------------------------------
# add_final() behavior
# ---------------------------------------------------------------------------

class TestAddFinal:
    def test_add_final_creates_segment(self, overlay):
        overlay.add_final("Final text")
        assert len(overlay._segments) == 1
        assert overlay._segments[0] == ("Final text", "final")

    def test_add_final_removes_trailing_partial(self, overlay):
        overlay.add_partial("part")
        overlay.add_final("final")
        assert len(overlay._segments) == 1
        assert overlay._segments[0] == ("final", "final")

    def test_add_final_removes_only_trailing_partial(self, visible_overlay):
        """add_final only pops the LAST segment if it's partial; earlier segments survive."""
        visible_overlay.add_final("First final")
        visible_overlay.add_partial("streaming")
        visible_overlay.add_final("Second final")
        # First final survives, trailing partial was popped, second final appended
        assert visible_overlay._segments == [
            ("First final", "final"),
            ("Second final", "final"),
        ]

    def test_add_final_renders_bright_color(self, visible_overlay):
        visible_overlay.add_final("bright text")
        html = visible_overlay._text_edit.toHtml()
        assert _TEXT_BRIGHT in html

    def test_add_final_html_escapes(self, visible_overlay):
        visible_overlay.add_final("<script>alert('x')</script>")
        html = visible_overlay._text_edit.toHtml()
        assert "<script>" not in html or "&lt;" in html

    def test_add_final_ampersand_escaped(self, visible_overlay):
        visible_overlay.add_final("A & B")
        html = visible_overlay._text_edit.toHtml()
        assert "&amp;" in html

    def test_multiple_finals_accumulate(self, overlay):
        overlay.add_final("First")
        overlay.add_final("Second")
        assert len(overlay._segments) == 2
        assert overlay._segments[0] == ("First", "final")
        assert overlay._segments[1] == ("Second", "final")


# ---------------------------------------------------------------------------
# set_enabled(False) disables methods
# ---------------------------------------------------------------------------

class TestSetEnabled:
    def test_set_enabled_false(self, overlay):
        overlay.set_enabled(False)
        assert overlay._enabled is False
        assert overlay.is_enabled is False

    def test_add_partial_noop_when_disabled(self, overlay):
        overlay.set_enabled(False)
        overlay.add_partial("Should not appear")
        assert overlay._segments == []

    def test_add_final_noop_when_disabled(self, overlay):
        """M1: add_final() honors _enabled just like add_partial()."""
        overlay.set_enabled(False)
        overlay.add_final("Should not appear")
        assert overlay._segments == []

    def test_show_noop_when_disabled(self, overlay):
        overlay.set_enabled(False)
        overlay.show()
        assert overlay._window is None

    def test_start_auto_dismiss_noop_when_disabled(self, overlay):
        overlay.set_enabled(False)
        overlay.start_auto_dismiss()
        assert overlay._auto_dismiss_timer is None

    def test_set_enabled_true_restores(self, overlay):
        overlay.set_enabled(False)
        overlay.set_enabled(True)
        assert overlay._enabled is True
        overlay.add_partial("Works again")
        assert len(overlay._segments) == 1

    def test_set_enabled_false_closes_window(self, visible_overlay):
        visible_overlay.set_enabled(False)
        # close() is called, which sets _window to None after deleteLater
        QApplication.processEvents()
        assert visible_overlay._window is None


# ---------------------------------------------------------------------------
# set_opacity() updates value
# ---------------------------------------------------------------------------

class TestSetOpacity:
    def test_set_opacity_updates_value(self, overlay):
        overlay.set_opacity(0.75)
        assert overlay._opacity == 0.75

    def test_set_opacity_clamps_low(self, overlay):
        overlay.set_opacity(0.1)
        assert overlay._opacity == 0.5  # clamped to min 0.5

    def test_set_opacity_clamps_high(self, overlay):
        overlay.set_opacity(1.5)
        assert overlay._opacity == 1.0

    def test_set_opacity_on_window(self, visible_overlay):
        visible_overlay.set_opacity(0.8)
        assert visible_overlay._window is not None
        assert visible_overlay._window.windowOpacity() == pytest.approx(0.8, abs=0.01)

    def test_set_opacity_before_window(self, overlay):
        overlay.set_opacity(0.6)
        assert overlay._opacity == 0.6
        # Window not created yet, no crash
        assert overlay._window is None

    def test_set_opacity_at_boundaries(self, overlay):
        overlay.set_opacity(0.5)
        assert overlay._opacity == 0.5
        overlay.set_opacity(1.0)
        assert overlay._opacity == 1.0


# ---------------------------------------------------------------------------
# set_font_size() updates value
# ---------------------------------------------------------------------------

class TestSetFontSize:
    def test_set_font_size_updates_value(self, overlay):
        overlay.set_font_size(18)
        assert overlay._font_size == 18

    def test_set_font_size_clamps_low(self, overlay):
        overlay.set_font_size(2)
        assert overlay._font_size == 8  # min

    def test_set_font_size_clamps_high(self, overlay):
        overlay.set_font_size(100)
        assert overlay._font_size == 36  # max

    def test_set_font_size_applies_stylesheet(self, visible_overlay):
        """MAJOR-1 fix: set_font_size must re-apply stylesheet, not just setFont()."""
        visible_overlay.set_font_size(20)
        assert visible_overlay._text_edit is not None
        ss = visible_overlay._text_edit.styleSheet()
        assert "font-size: 20px" in ss

    def test_set_font_size_before_window(self, overlay):
        """Setting font size before window exists should just update the stored value."""
        overlay.set_font_size(22)
        assert overlay._font_size == 22
        assert overlay._text_edit is None

    def test_set_font_size_at_boundaries(self, overlay):
        overlay.set_font_size(8)
        assert overlay._font_size == 8
        overlay.set_font_size(36)
        assert overlay._font_size == 36

    def test_set_font_size_default_value(self, overlay):
        assert overlay._font_size == _DEFAULT_FONT_SIZE


# ---------------------------------------------------------------------------
# set_max_height() updates value
# ---------------------------------------------------------------------------

class TestSetMaxHeight:
    def test_set_max_height_updates_value(self, overlay):
        overlay.set_max_height(400)
        assert overlay._max_height == 400

    def test_set_max_height_clamps_low(self, overlay):
        overlay.set_max_height(10)
        assert overlay._max_height == 100  # min

    def test_set_max_height_clamps_high(self, overlay):
        overlay.set_max_height(9999)
        assert overlay._max_height == 600  # max

    def test_set_max_height_applies_to_window(self, visible_overlay):
        """MAJOR-2 regression: max_height must be applied when window is created."""
        visible_overlay.set_max_height(400)
        assert visible_overlay._window is not None
        assert visible_overlay._window.maximumHeight() == 400

    def test_set_max_height_before_window_created(self, overlay):
        """Setting max_height before window exists should update stored value."""
        overlay.set_max_height(500)
        assert overlay._max_height == 500
        assert overlay._window is None

    def test_max_height_applied_on_show(self, qapp):
        """MAJOR-2 fix: _build_window() must apply self._max_height."""
        ov = TranscriptOverlay()
        ov.set_max_height(450)  # set BEFORE show
        ov.show()
        QTest.qWait(50)
        QApplication.processEvents()
        assert ov._window is not None
        assert ov._window.maximumHeight() == 450
        ov.close()
        QApplication.processEvents()

    def test_set_max_height_at_boundaries(self, overlay):
        overlay.set_max_height(100)
        assert overlay._max_height == 100
        overlay.set_max_height(600)
        assert overlay._max_height == 600


# ---------------------------------------------------------------------------
# set_auto_dismiss_seconds() updates value
# ---------------------------------------------------------------------------

class TestSetAutoDismissSeconds:
    def test_set_auto_dismiss_updates_value(self, overlay):
        overlay.set_auto_dismiss_seconds(5.0)
        assert overlay._auto_dismiss_seconds == 5.0

    def test_set_auto_dismiss_clamps_low(self, overlay):
        overlay.set_auto_dismiss_seconds(0.1)
        assert overlay._auto_dismiss_seconds == 1.0  # min

    def test_set_auto_dismiss_clamps_high(self, overlay):
        overlay.set_auto_dismiss_seconds(100.0)
        assert overlay._auto_dismiss_seconds == 30.0  # max

    def test_set_auto_dismiss_at_boundaries(self, overlay):
        overlay.set_auto_dismiss_seconds(1.0)
        assert overlay._auto_dismiss_seconds == 1.0
        overlay.set_auto_dismiss_seconds(30.0)
        assert overlay._auto_dismiss_seconds == 30.0


# ---------------------------------------------------------------------------
# Window creation and show/hide
# ---------------------------------------------------------------------------

class TestWindowState:
    def test_show_creates_window(self, visible_overlay):
        assert visible_overlay._window is not None
        assert visible_overlay._title_bar is not None
        assert visible_overlay._title_label is not None
        assert visible_overlay._close_button is not None
        assert visible_overlay._text_edit is not None

    def test_show_sets_opacity(self, visible_overlay):
        assert visible_overlay._window.windowOpacity() >= 0.0

    def test_show_sets_minimum_size(self, visible_overlay):
        geo = visible_overlay._window.minimumSize()
        assert geo.width() == _MIN_WIDTH
        assert geo.height() == _MIN_HEIGHT

    def test_window_is_frameless(self, visible_overlay):
        flags = visible_overlay._window.windowFlags()
        assert bool(flags & Qt.WindowType.FramelessWindowHint)
        assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)

    def test_window_is_translucent(self, visible_overlay):
        assert visible_overlay._window.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

    def test_window_title(self, visible_overlay):
        assert visible_overlay._window.windowTitle() == "Transcript"

    def test_text_edit_is_readonly(self, visible_overlay):
        assert visible_overlay._text_edit.isReadOnly()

    def test_window_default_size(self, visible_overlay):
        geo = visible_overlay._window.size()
        assert geo.width() == _DEFAULT_WIDTH
        assert geo.height() == _DEFAULT_HEIGHT

    def test_show_when_disabled_is_noop(self, overlay):
        overlay.set_enabled(False)
        overlay.show()
        assert overlay._window is None


# ---------------------------------------------------------------------------
# close() behavior
# ---------------------------------------------------------------------------

class TestClose:
    def test_close_clears_window(self, visible_overlay):
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._window is None

    def test_close_clears_segments(self, visible_overlay):
        visible_overlay.add_partial("text")
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._segments == []

    def test_close_clears_widget_refs(self, visible_overlay):
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._title_bar is None
        assert visible_overlay._title_label is None
        assert visible_overlay._close_button is None
        assert visible_overlay._text_edit is None

    def test_close_multiple_calls_safe(self, visible_overlay):
        visible_overlay.close()
        QApplication.processEvents()
        visible_overlay.close()  # should not crash


# ---------------------------------------------------------------------------
# Segment state transitions
# ---------------------------------------------------------------------------

class TestStateTransitions:
    def test_partial_then_final(self, overlay):
        overlay.add_partial("Hel")
        overlay.add_final("Hello")
        assert overlay._segments == [("Hello", "final")]

    def test_final_then_partial(self, overlay):
        overlay.add_final("First")
        overlay.add_partial("Sec")
        assert overlay._segments == [("First", "final"), ("Sec", "partial")]

    def test_partial_replaced_multiple_times(self, overlay):
        overlay.add_partial("a")
        overlay.add_partial("ab")
        overlay.add_partial("abc")
        assert len(overlay._segments) == 1
        assert overlay._segments[0] == ("abc", "partial")

    def test_multiple_finals(self, overlay):
        overlay.add_final("One")
        overlay.add_final("Two")
        overlay.add_final("Three")
        assert len(overlay._segments) == 3
        assert all(k == "final" for _, k in overlay._segments)

    def test_interleaved_partials_and_finals(self, overlay):
        overlay.add_partial("a")
        overlay.add_final("A")
        overlay.add_partial("b")
        overlay.add_final("B")
        assert overlay._segments == [("A", "final"), ("B", "final")]

    def test_clear_after_close(self, visible_overlay):
        visible_overlay.add_partial("temp")
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._segments == []


# ---------------------------------------------------------------------------
# HTML rendering details
# ---------------------------------------------------------------------------

class TestRendering:
    def test_newline_rendered_as_br(self, visible_overlay):
        visible_overlay.add_final("Line1\nLine2")
        html = visible_overlay._text_edit.toHtml()
        assert "Line1" in html
        assert "Line2" in html

    def test_partial_text_rendered(self, visible_overlay):
        visible_overlay.add_partial("partial content")
        assert "partial content" in visible_overlay._text_edit.toPlainText()

    def test_final_text_rendered(self, visible_overlay):
        visible_overlay.add_final("final content")
        assert "final content" in visible_overlay._text_edit.toPlainText()

    def test_segments_cleared_after_render_with_empty(self, visible_overlay):
        visible_overlay.add_final("text")
        # close() clears segments
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._segments == []


# ---------------------------------------------------------------------------
# M4: theme tokens + accessible close button
# ---------------------------------------------------------------------------

class TestThemeTokensAndCloseButton:
    def test_overlay_imports_theme_tokens(self):
        import voice_typing.ui.transcript_overlay as ov_mod
        from voice_typing.ui import _theme as theme

        assert ov_mod._BG_COLOR == theme.COLOR_OVERLAY_BG
        assert ov_mod._BORDER_COLOR == theme.COLOR_OVERLAY_BORDER
        assert ov_mod._TEXT_BRIGHT == theme.COLOR_OVERLAY_TEXT_BRIGHT
        assert ov_mod._TEXT_DIM == theme.COLOR_OVERLAY_TEXT_DIM
        assert ov_mod._HOVER_BG == theme.COLOR_OVERLAY_HOVER_BG

    def test_no_hardcoded_hex_in_overlay(self):
        import pathlib
        import re

        text = pathlib.Path("voice_typing/ui/transcript_overlay.py").read_text(
            encoding="utf-8"
        )
        assert re.findall(r"#[0-9a-fA-F]{3,8}\b", text) == []

    def test_close_button_meets_touch_target_and_focus(self, visible_overlay):
        from PySide6.QtCore import Qt

        btn = visible_overlay._close_button
        assert btn is not None
        assert btn.width() >= 28 and btn.height() >= 28
        assert btn.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert ":focus" in btn.styleSheet()


# ---------------------------------------------------------------------------
# UX Phase C: partial blue + caret blink, finals white
# ---------------------------------------------------------------------------

class TestPhaseCPartialCaret:
    def test_partial_renders_blue(self, visible_overlay):
        from voice_typing.ui import _theme as theme

        visible_overlay.add_partial("streaming")
        html = visible_overlay._text_edit.toHtml()
        assert theme.COLOR_OVERLAY_PARTIAL_BLUE in html

    def test_final_renders_bright_not_blue(self, visible_overlay):
        from voice_typing.ui import _theme as theme

        visible_overlay.add_final("done")
        html = visible_overlay._text_edit.toHtml()
        assert theme.COLOR_OVERLAY_TEXT_BRIGHT in html

    def test_caret_timer_exists_and_interval(self, visible_overlay):
        from voice_typing.ui import _theme as theme

        assert visible_overlay._caret_timer is not None
        assert visible_overlay._caret_timer.interval() == theme.OVERLAY_CARET_BLINK_MS == 530

    def test_caret_blink_toggles_and_rerenders(self, visible_overlay):
        visible_overlay.add_partial("live")
        before = visible_overlay._caret_visible
        visible_overlay._on_caret_blink()
        assert visible_overlay._caret_visible is not before

    def test_caret_absent_without_partial(self, visible_overlay):
        from voice_typing.ui import _theme as theme

        visible_overlay.add_final("only final")
        visible_overlay._caret_visible = True
        visible_overlay._render_segments()
        html = visible_overlay._text_edit.toHtml()
        assert theme.COLOR_OVERLAY_CARET not in html

    def test_overlay_imports_phase_c_tokens(self):
        import voice_typing.ui.transcript_overlay as ov_mod
        from voice_typing.ui import _theme as theme

        assert ov_mod._PARTIAL_BLUE == theme.COLOR_OVERLAY_PARTIAL_BLUE
        assert ov_mod._CARET_COLOR == theme.COLOR_OVERLAY_CARET
        assert ov_mod._PROGRESS_BG == theme.COLOR_OVERLAY_PROGRESS_BG
        assert ov_mod._PROGRESS_FILL == theme.COLOR_OVERLAY_PROGRESS_FILL


# ---------------------------------------------------------------------------
# UX Phase C: pin (suppress dismiss) + determinate progress + pause/resume
# ---------------------------------------------------------------------------

class TestPhaseCPinProgress:
    def test_default_unpinned(self, overlay):
        assert overlay.is_pinned is False

    def test_set_pinned_updates_state_and_button(self, visible_overlay):
        received = []
        visible_overlay.signals.pin_toggled.connect(received.append)
        visible_overlay.set_pinned(True)
        assert visible_overlay.is_pinned is True
        assert visible_overlay._pin_button.isChecked() is True
        assert received == [True]
        visible_overlay.set_pinned(False)
        assert visible_overlay.is_pinned is False
        assert received == [True, False]

    def test_pin_button_is_checkable(self, visible_overlay):
        assert visible_overlay._pin_button.isCheckable()

    def test_pinned_suppresses_auto_dismiss(self, visible_overlay):
        visible_overlay.set_pinned(True)
        visible_overlay.start_auto_dismiss()
        assert (
            visible_overlay._auto_dismiss_timer is None
            or not visible_overlay._auto_dismiss_timer.isActive()
        )
        assert visible_overlay._progress_active is False

    def test_unpinned_starts_determinate_progress(self, visible_overlay):
        visible_overlay.set_pinned(False)
        visible_overlay.start_auto_dismiss()
        assert visible_overlay._progress_active is True
        assert visible_overlay._progress_timer is not None
        assert visible_overlay._progress_timer.interval() == 50
        assert visible_overlay._progress_bar.maximum() == visible_overlay._progress_total_ms
        # 3px bar visible while unpinned countdown runs.
        assert visible_overlay._progress_bar.isVisible()

    def test_progress_bar_hidden_when_pinned(self, visible_overlay):
        visible_overlay.set_pinned(False)
        visible_overlay.start_auto_dismiss()
        assert visible_overlay._progress_bar.isVisible()
        visible_overlay.set_pinned(True)
        assert not visible_overlay._progress_bar.isVisible()

    def test_progress_bar_height_3px(self, visible_overlay):
        from voice_typing.ui import _theme as theme

        assert theme.OVERLAY_PROGRESS_HEIGHT == 3
        assert visible_overlay._progress_bar.maximumHeight() == 3 or \
            visible_overlay._progress_bar.height() <= 32  # offscreen layout tolerance
        assert "min-height: 3px" in visible_overlay._progress_bar.styleSheet() or \
            f"{theme.OVERLAY_PROGRESS_HEIGHT}px" in visible_overlay._progress_bar.styleSheet()

    def test_pause_resume_progress(self, visible_overlay):
        visible_overlay.set_pinned(False)
        visible_overlay.start_auto_dismiss()
        visible_overlay.pause()
        assert visible_overlay._progress_paused is True
        visible_overlay.resume()
        assert visible_overlay._progress_paused is False

    def test_pause_resume_safe_when_idle(self, overlay):
        overlay.pause()  # must not crash
        overlay.resume()  # must not crash
        assert overlay._progress_active is False

    def test_hover_pauses_and_resumes(self, visible_overlay):
        visible_overlay.set_pinned(False)
        visible_overlay.start_auto_dismiss()
        visible_overlay._on_hover_changed(True)
        assert visible_overlay._progress_paused is True
        visible_overlay._on_hover_changed(False)
        assert visible_overlay._progress_paused is False


# ---------------------------------------------------------------------------
# UX Phase C: copy finals-only + edit-before-inject
# ---------------------------------------------------------------------------

class TestPhaseCCopyEdit:
    def test_copy_button_exists(self, visible_overlay):
        assert visible_overlay._copy_button is not None

    def test_copy_finals_only(self, visible_overlay, qapp):
        from unittest.mock import MagicMock

        visible_overlay.add_final("hello")
        visible_overlay.add_partial("streaming ignored")
        visible_overlay.add_final("world")
        mock_clip = MagicMock()
        orig = QApplication.clipboard
        QApplication.clipboard = staticmethod(lambda *a, **k: mock_clip)
        try:
            text = visible_overlay.copy_to_clipboard()
        finally:
            QApplication.clipboard = orig
        assert text == "hello world"
        mock_clip.setText.assert_called_once_with("hello world")

    def test_copy_empty_when_no_finals(self, visible_overlay, qapp):
        from unittest.mock import MagicMock

        visible_overlay.add_partial("only partial")
        mock_clip = MagicMock()
        orig = QApplication.clipboard
        QApplication.clipboard = staticmethod(lambda *a, **k: mock_clip)
        try:
            text = visible_overlay.copy_to_clipboard()
        finally:
            QApplication.clipboard = orig
        assert text == ""
        mock_clip.setText.assert_not_called()

    def test_copy_clicked_signal(self, visible_overlay, qapp):
        from unittest.mock import MagicMock

        received = []
        visible_overlay.signals.copy_clicked.connect(lambda: received.append(True))
        mock_clip = MagicMock()
        orig = QApplication.clipboard
        QApplication.clipboard = staticmethod(lambda *a, **k: mock_clip)
        try:
            visible_overlay.add_final("abc")
            visible_overlay._on_copy_clicked()
        finally:
            QApplication.clipboard = orig
        assert received == [True]

    def test_edit_line_exists(self, visible_overlay):
        from PySide6.QtWidgets import QLineEdit

        assert isinstance(visible_overlay._edit_line, QLineEdit)

    def test_edit_commit_replaces_finals_and_emits(self, visible_overlay):
        received = []
        visible_overlay.signals.edit_committed.connect(received.append)
        visible_overlay.add_final("old one")
        visible_overlay.add_final("old two")
        visible_overlay.add_partial("stale partial")
        visible_overlay._edit_line.setText("  edited text  ")
        visible_overlay._on_edit_return_pressed()
        assert received == ["edited text"]
        assert visible_overlay._segments == [("edited text", "final")]
        assert visible_overlay._edit_line.text() == ""

    def test_edit_empty_ignored(self, visible_overlay):
        received = []
        visible_overlay.signals.edit_committed.connect(received.append)
        visible_overlay.add_final("keep")
        visible_overlay._edit_line.setText("   ")
        visible_overlay._on_edit_return_pressed()
        assert received == []
        assert visible_overlay._segments == [("keep", "final")]


# ---------------------------------------------------------------------------
# UX Phase C: geometry (top-edge drag + SE grip + debounced signal)
# ---------------------------------------------------------------------------

class TestPhaseCGeometry:
    def test_keeps_show_without_activating(self, visible_overlay):
        from PySide6.QtCore import Qt

        assert visible_overlay._window.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating
        )

    def test_size_grip_exists(self, visible_overlay):
        from PySide6.QtWidgets import QSizeGrip

        assert isinstance(visible_overlay._size_grip, QSizeGrip)

    def test_set_geometry_from_settings_applies(self, visible_overlay):
        visible_overlay.set_geometry_from_settings(10, 20, 450, 200)
        geo = visible_overlay._window.geometry()
        assert (geo.x(), geo.y()) == (10, 20)
        assert (geo.width(), geo.height()) == (450, 200)

    def test_set_geometry_pending_before_show(self, qapp):
        ov = TranscriptOverlay()
        try:
            ov.set_geometry_from_settings(11, 22, 400, 150)
            assert ov._window is None
            ov.show()
            from PySide6.QtTest import QTest
            QTest.qWait(50)
            QApplication.processEvents()
            geo = ov._window.geometry()
            assert (geo.x(), geo.y()) == (11, 22)
        finally:
            ov.close()
            QApplication.processEvents()

    def test_geometry_changed_debounced(self, visible_overlay, qapp):
        from PySide6.QtTest import QTest

        received = []
        visible_overlay.signals.geometry_changed.connect(
            lambda x, y, w, h: received.append((x, y, w, h))
        )
        visible_overlay._window.move(40, 50)
        visible_overlay._window.move(41, 51)
        QApplication.processEvents()
        assert received == []  # debounced, not immediate
        QTest.qWait(450)
        QApplication.processEvents()
        assert len(received) == 1
        assert received[0][:2] == (41, 51)

    def test_close_stops_timers(self, visible_overlay):
        visible_overlay.set_pinned(False)
        visible_overlay.start_auto_dismiss()
        assert visible_overlay._caret_timer is not None
        visible_overlay.close()
        QApplication.processEvents()
        assert visible_overlay._window is None
        assert visible_overlay._caret_timer is None
        assert visible_overlay._progress_timer is None
        assert visible_overlay._auto_dismiss_timer is None
        assert visible_overlay._geometry_debounce is None


# ---------------------------------------------------------------------------
# Phase C reviewer follow-ups: M1/M2/M3 + m1/m2
# ---------------------------------------------------------------------------

class TestReviewerFollowUps:
    def test_add_final_noop_when_disabled(self, overlay):
        overlay.set_enabled(False)
        overlay.add_final("blocked")
        assert overlay._segments == []

    def test_add_final_empty_ignored(self, overlay):
        overlay.add_final("")
        assert overlay._segments == []

    def test_caret_timer_stops_when_final_removes_partial(
        self, visible_overlay
    ):
        visible_overlay.add_partial("live")
        assert visible_overlay._caret_timer is not None
        assert visible_overlay._caret_timer.isActive()
        visible_overlay.add_final("done")
        QApplication.processEvents()
        assert not visible_overlay._caret_timer.isActive()

    def test_caret_timer_stops_on_hide(self, visible_overlay):
        visible_overlay.add_partial("live")
        assert visible_overlay._caret_timer.isActive()
        visible_overlay.hide()
        QApplication.processEvents()
        assert not visible_overlay._caret_timer.isActive()
        # Finish fade-out path as well.
        visible_overlay._on_fade_out_finished()
        QApplication.processEvents()
        assert not visible_overlay._caret_timer.isActive()

    def test_caret_blink_stops_timer_without_partial(
        self, visible_overlay
    ):
        visible_overlay.add_partial("live")
        assert visible_overlay._caret_timer.isActive()
        visible_overlay.add_final("done")
        # Simulate a stray blink tick with no partial trailing.
        visible_overlay._on_caret_blink()
        assert not visible_overlay._caret_timer.isActive()

    def test_focus_policies_no_steal(self, visible_overlay):
        from PySide6.QtCore import Qt

        assert visible_overlay._window.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating
        )
        assert visible_overlay._text_edit.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert visible_overlay._edit_line.focusPolicy() == Qt.FocusPolicy.ClickFocus

    def test_edit_commit_clears_focus(self, visible_overlay):
        received = []
        visible_overlay.signals.edit_committed.connect(received.append)
        visible_overlay.add_final("old")
        visible_overlay._edit_line.setText("fixed")
        visible_overlay._on_edit_return_pressed()
        assert received == ["fixed"]
        assert not visible_overlay._edit_line.hasFocus()

    def test_programmatic_geometry_does_not_emit(
        self, visible_overlay, qapp
    ):
        from PySide6.QtTest import QTest

        received = []
        visible_overlay.signals.geometry_changed.connect(
            lambda x, y, w, h: received.append((x, y, w, h))
        )
        visible_overlay.set_geometry_from_settings(10, 20, 450, 200)
        QApplication.processEvents()
        QTest.qWait(450)
        QApplication.processEvents()
        assert received == []

    def test_overlay_clamps_offscreen_xy(self, qapp):
        from PySide6.QtWidgets import QApplication as _QA

        ov = TranscriptOverlay()
        try:
            ov.set_geometry_from_settings(99999, 99999, 450, 200)
            ov.show()
            from PySide6.QtTest import QTest

            QTest.qWait(50)
            QApplication.processEvents()
            geo = ov._window.geometry()
            screen = _QA.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                assert geo.x() <= avail.x() + avail.width() - 100
                assert geo.y() <= avail.y() + avail.height() - 50
        finally:
            ov.close()
            QApplication.processEvents()
