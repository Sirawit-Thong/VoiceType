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