# tests/test_status_bar.py
import os

# Must be set before PySide6 is imported so widgets can run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voice_typing.ui.status_bar import StatusBar, _WaveVisualizer


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def bar(qapp):
    b = StatusBar()
    b.show()
    yield b
    b.close()
    QTest.qWait(200)
    QApplication.processEvents()


def test_set_level_clamps_and_updates(bar):
    wave = bar._wave
    assert wave is not None
    bar.set_level(-0.1)
    assert wave._level == 0.0
    bar.set_level(1.5)
    assert wave._level == 1.0
    bar.set_level(0.5)
    assert wave._level == 0.5


def test_capsule_styles_and_dimensions(bar):
    assert bar.style == "pill"
    assert bar._window.width() == StatusBar.EXPANDED_WIDTH

    bar.set_style("dot")
    assert bar.style == "dot"
    QTest.qWait(250)
    assert bar._window.width() == StatusBar.COLLAPSED_WIDTH

    bar.set_style("pill")
    assert bar.style == "pill"
    QTest.qWait(250)
    assert bar._window.width() == StatusBar.EXPANDED_WIDTH


def test_dot_mode_expands_on_recording(bar):
    bar.set_style("dot")
    QTest.qWait(250)
    assert bar._window.width() == StatusBar.COLLAPSED_WIDTH

    bar.update_recording_state(True)
    QTest.qWait(250)
    assert bar._window.width() == StatusBar.EXPANDED_WIDTH

    bar.update_recording_state(False)
    QTest.qWait(250)
    assert bar._window.width() == StatusBar.COLLAPSED_WIDTH


def test_show_close_no_crash(bar):
    bar.close()
    bar.close()  # re-entrant close while fading must be a no-op, not a crash
    tries = 30
    while bar._window is not None and tries > 0:
        QTest.qWait(10)
        tries -= 1
    assert bar._window is None


def test_pulse_runs_only_while_listening(bar):
    bar.set_state("ready")
    assert bar._pulse_anim is None
    bar.set_state("listening")
    assert bar._pulse_anim is not None
    bar.set_state("listening")  # repeated listening must not stack animations
    assert bar._pulse_anim is not None
    bar.set_state("processing")
    assert bar._pulse_anim is None
    assert bar._pulse_effect.opacity() == 1.0
    bar.set_state("listening")
    assert bar._pulse_anim is not None
    bar.update_recording_state(False)
    assert bar._pulse_anim is None
    assert bar._pulse_effect.opacity() == 1.0


def test_wave_visualizer_paint(qapp):
    wave = _WaveVisualizer()
    wave.set_level(0.7)
    wave.set_color("#ea4335")
    assert wave._level == 0.7
    assert wave._color.name() == "#ea4335"
    wave.repaint()


def test_set_opacity(bar):
    bar.set_opacity(0.7)
    assert bar._opacity == pytest.approx(0.7)

    bar.set_opacity(0.2)  # clamps to 0.5
    assert bar._opacity == pytest.approx(0.5)

    bar.set_opacity(1.5)  # clamps to 1.0
    assert bar._opacity == pytest.approx(1.0)


# ── UX Phase A: capsule states ────────────────────────────────────────

def test_canonical_states_distinct_colors(bar):
    from voice_typing.ui import _theme as theme

    expected = {
        "idle": theme.COLOR_READY,
        "listening": theme.COLOR_LISTENING,
        "processing": theme.COLOR_PROCESSING,
        "reconnecting": theme.COLOR_RECONNECTING,
        "error-dead": theme.COLOR_ERROR_DEAD,
    }
    seen = set()
    for state, color in expected.items():
        bar.set_state(state)
        assert bar._state == state
        assert bar._state_color == color
        seen.add(color)
    assert len(seen) == 5


def test_aliases_ready_and_error(bar):
    from voice_typing.ui import _theme as theme

    bar.set_state("ready")
    assert bar._state == "idle"
    assert bar._state_color == theme.COLOR_READY
    bar.set_state("error", "oops")
    assert bar._state == "error-dead"
    assert bar._state_color == theme.COLOR_ERROR_DEAD


def test_processing_retained(bar):
    from voice_typing.ui import _theme as theme

    bar.set_state("processing", "Working...")
    assert bar._state == "processing"
    assert bar._state_color == theme.COLOR_PROCESSING
    assert bar._status_label.text() == "Working..."


def test_distinct_tooltips_per_state(bar):
    tips = {}
    for state in ("idle", "listening", "processing", "reconnecting", "error-dead"):
        bar.set_state(state)
        tips[state] = bar._mic_button.toolTip()
    assert len(set(tips.values())) == 5


def test_mic_disabled_with_explanatory_tooltip(bar):
    bar.set_state("reconnecting", "Reconnecting...")
    assert not bar._mic_button.isEnabled()
    tip = bar._mic_button.toolTip().lower()
    assert "reconnect" in tip

    bar.set_state("error-dead", "boom")
    assert not bar._mic_button.isEnabled()
    tip = bar._mic_button.toolTip().lower()
    assert "api key" in tip or "network" in tip or "retry" in tip

    for state in ("idle", "listening", "processing"):
        bar.set_state(state)
        assert bar._mic_button.isEnabled()


def test_touch_targets_min_28(bar):
    from voice_typing.ui._theme import TOUCH_TARGET_MIN

    for btn in (bar._mic_button, bar._tray_btn, bar._menu_button):
        assert btn is not None
        assert btn.minimumWidth() >= TOUCH_TARGET_MIN
        assert btn.minimumHeight() >= TOUCH_TARGET_MIN
        assert btn.width() >= 28 and btn.height() >= 28


def test_strong_focus_and_visible_focus_ring(bar):
    for btn in (bar._mic_button, bar._tray_btn, bar._menu_button):
        assert btn.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert ":focus" in btn.styleSheet()


def test_wave_dim_only_when_idle(bar):
    from voice_typing.ui._theme import OPACITY_IDLE_WAVE_DIM

    bar.set_state("idle")
    assert bar._wave_opacity is not None
    assert bar._wave_opacity.opacity() == pytest.approx(OPACITY_IDLE_WAVE_DIM)
    bar.set_state("listening")
    assert bar._wave_opacity.opacity() == pytest.approx(1.0)
    bar.set_state("processing")
    assert bar._wave_opacity.opacity() == pytest.approx(1.0)
    bar.set_state("reconnecting")
    assert bar._wave_opacity.opacity() == pytest.approx(1.0)
    bar.set_state("error-dead")
    assert bar._wave_opacity.opacity() == pytest.approx(1.0)


def test_pulse_only_listening_and_reconnecting(bar):
    bar.set_state("idle")
    assert bar._pulse_anim is None
    bar.set_state("listening")
    assert bar._pulse_anim is not None
    bar.set_state("reconnecting")
    assert bar._pulse_anim is not None
    bar.set_state("processing")
    assert bar._pulse_anim is None
    bar.set_state("error-dead")
    assert bar._pulse_anim is None


def test_no_hardcoded_colors_in_status_bar():
    import pathlib
    import re

    text = pathlib.Path("voice_typing/ui/status_bar.py").read_text(encoding="utf-8")
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b", text) == []
    assert "rgba(" not in text


def test_level_meter_tooltip_while_audio_flows(bar):
    assert bar._wave.toolTip() == "Level meter active while audio flows"


def test_unknown_state_falls_back_to_idle_with_warning(bar, caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="voice_typing.ui.status_bar"):
        bar.set_state("bogus-state", "hello")
    assert bar._state == "idle"
    assert any("bogus-state" in r.message for r in caplog.records)


def test_pre_show_text_preserved(qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    bar = StatusBar()
    bar.set_state("listening", "hello-preshow")
    assert bar._pending_text == "hello-preshow"
    bar.show()
    QTest.qWait(50)
    QApplication.processEvents()
    assert bar._status_label.text() == "hello-preshow"
    bar.close()
    QTest.qWait(200)
    QApplication.processEvents()


def test_no_runtime_asserts_in_status_bar():
    import pathlib

    text = pathlib.Path("voice_typing/ui/status_bar.py").read_text(encoding="utf-8")
    # m6: geometry parity is verified by tests, never by runtime assert.
    assert "\nassert " not in text
    assert "\n    assert " not in text