# tests/test_status_bar.py
import os

# Must be set before PySide6 is imported so widgets can run headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from voice_typing.ui.status_bar import StatusBar


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
    QTest.qWait(250)  # let the fade-out finish and animations be released
    QApplication.processEvents()


def test_set_level_clamps_and_updates(bar):
    meter = bar._meter
    assert meter is not None
    bar.set_level(-0.1)
    assert meter.lit_segments == 0
    bar.set_level(1.5)
    assert meter.lit_segments == 5
    bar.set_level(0.5)
    assert meter.lit_segments == 3


def test_meter_hidden_when_not_recording(bar):
    meter = bar._meter
    assert meter is not None
    bar.update_recording_state(False)
    assert not meter.isVisible()
    bar.update_recording_state(True)
    assert meter.isVisible()
    bar.update_recording_state(False)
    assert not meter.isVisible()


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


def test_collapse_button_hides_window(bar):
    collapse = bar._collapse_button
    assert collapse is not None
    assert bar._window is not None
    QTest.mouseClick(collapse, Qt.MouseButton.LeftButton)
    tries = 30
    while bar._window is not None and tries > 0:
        QTest.qWait(10)
        tries -= 1
    assert bar._window is None  # collapsed (faded out and released)


def test_show_after_collapse_rebuilds(bar):
    QTest.mouseClick(bar._collapse_button, Qt.MouseButton.LeftButton)
    tries = 30
    while bar._window is not None and tries > 0:
        QTest.qWait(10)
        tries -= 1
    assert bar._window is None
    bar.show()
    assert bar._window is not None
    assert bar._window.isVisible()