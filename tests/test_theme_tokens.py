# tests/test_theme_tokens.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from voice_typing.ui import _theme as theme


def test_state_colors_present_and_distinct():
    assert theme.COLOR_READY == "#34a853"
    assert theme.COLOR_LISTENING == "#ea4335"
    assert theme.COLOR_PROCESSING == "#fbbc04"
    assert theme.COLOR_RECONNECTING == "#fb8c00"
    assert theme.COLOR_ERROR_DEAD == "#9aa0a6"
    # Reconnecting must be visually distinct from processing.
    assert theme.COLOR_RECONNECTING != theme.COLOR_PROCESSING
    assert len({theme.COLOR_READY, theme.COLOR_LISTENING, theme.COLOR_PROCESSING,
                theme.COLOR_RECONNECTING, theme.COLOR_ERROR_DEAD}) == 5


def test_capsule_and_text_tokens():
    assert theme.COLOR_CAPSULE_BG == "rgba(26, 27, 30, 0.95)"
    assert theme.COLOR_CAPSULE_BORDER == "#3c4043"
    assert theme.COLOR_TEXT_PRIMARY == "#e8eaed"
    assert theme.COLOR_TEXT_MUTED == "#9aa0a6"


def test_font_geometry_opacity_tokens():
    assert theme.FONT_FAMILY == "'Segoe UI', sans-serif"
    assert theme.FONT_SIZE_STATUS == 13
    assert theme.FONT_SIZES["status"] == 13
    assert theme.FONT_WEIGHT_STATUS == theme.FONT_WEIGHT_MEDIUM == 500
    assert theme.RADIUS_CAPSULE == 18
    assert theme.CAPSULE_HEIGHT == 36
    assert theme.TOUCH_TARGET_MIN == 28
    assert theme.OPACITY_DEFAULT == 0.94
    assert theme.OPACITY_IDLE_WAVE_DIM == 0.45


def test_capsule_stylesheet_builder():
    default_css = theme.capsule_stylesheet()
    assert str(theme.RADIUS_CAPSULE) in default_css
    assert theme.COLOR_CAPSULE_BORDER in default_css
    assert theme.COLOR_CAPSULE_BG in default_css
    accent_css = theme.capsule_stylesheet(theme.COLOR_LISTENING)
    assert theme.COLOR_LISTENING in accent_css
    assert "1.5px" in accent_css


def test_control_button_stylesheet_builder():
    css = theme.control_button_stylesheet()
    assert ":focus" in css
    assert ":disabled" in css
    assert ":hover" in css
    assert theme.COLOR_TEXT_MUTED in css
    assert theme.COLOR_FOCUS_RING in css


def test_focus_ring_stylesheet_builder():
    css = theme.focus_ring_stylesheet()
    assert ":focus" in css
    assert theme.COLOR_FOCUS_RING in css
    custom = theme.focus_ring_stylesheet("#ffffff")
    assert "#ffffff" in custom


def test_overlay_and_tray_tokens_preserve_visuals():
    assert theme.COLOR_OVERLAY_BG == "#1a1b1e"
    assert theme.COLOR_OVERLAY_BORDER == "#3c4043"
    assert theme.COLOR_OVERLAY_TEXT_BRIGHT == "#e8eaed"
    assert theme.COLOR_OVERLAY_TEXT_DIM == "#888888"
    assert theme.COLOR_OVERLAY_HOVER_BG == "rgba(255, 255, 255, 0.08)"
    assert theme.COLOR_TRAY_FALLBACK_BLUE == "#1a73e8"


def test_overlay_phase_c_tokens():
    # Partial blue is the focus blue; caret matches it; 3px progress bar.
    assert theme.COLOR_OVERLAY_PARTIAL_BLUE == "#8ab4f8"
    assert theme.COLOR_OVERLAY_CARET == "#8ab4f8"
    assert theme.COLOR_OVERLAY_PROGRESS_FILL == "#8ab4f8"
    assert theme.COLOR_OVERLAY_PROGRESS_BG == "#2b2d31"
    assert theme.OVERLAY_PROGRESS_HEIGHT == 3
    assert theme.OVERLAY_CARET_BLINK_MS == 530
    # Partial must differ from legacy dim gray and finals white.
    assert theme.COLOR_OVERLAY_PARTIAL_BLUE != theme.COLOR_OVERLAY_TEXT_DIM
    assert theme.COLOR_OVERLAY_PARTIAL_BLUE != theme.COLOR_OVERLAY_TEXT_BRIGHT
