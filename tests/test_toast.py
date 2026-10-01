# tests/test_toast.py
"""UX Phase B: ToastManager tests (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from voice_typing.ui import _theme as theme
from voice_typing.ui.toast import ToastManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _buttons(mgr):
    assert mgr._window is not None
    return {
        b.text(): b
        for b in mgr._window.findChildren(QPushButton)
    }


def test_theme_toast_tokens_reuse_palette():
    # Transient yellow / persistent red accents reuse capsule palette.
    assert theme.COLOR_TOAST_TRANSIENT_ACCENT == "#fbbc04"
    assert theme.COLOR_TOAST_PERSISTENT_ACCENT == "#ea4335"
    assert theme.COLOR_TOAST_BG == "#1a1b1e"
    assert theme.COLOR_TOAST_BG == theme.COLOR_OVERLAY_BG
    assert theme.COLOR_TOAST_TRANSIENT_ACCENT == theme.COLOR_PROCESSING
    assert theme.COLOR_TOAST_PERSISTENT_ACCENT == theme.COLOR_LISTENING
    assert theme.TOAST_RADIUS == 8
    assert theme.TOAST_FADE_IN_MS == 150
    assert theme.TOAST_FADE_OUT_MS == 120
    assert theme.TOAST_TRANSIENT_MS == 3000


def test_toast_stylesheet_uses_theme():
    css = theme.toast_stylesheet(theme.COLOR_TOAST_TRANSIENT_ACCENT)
    assert theme.COLOR_TOAST_TRANSIENT_ACCENT in css
    assert theme.COLOR_TOAST_BG in css
    assert str(theme.TOAST_RADIUS) in css
    assert ":focus" in css


def test_transient_content(qapp):
    mgr = ToastManager()
    try:
        mgr.show_transient("reconnecting notice")
        assert mgr.mode == "transient"
        assert mgr.message == "reconnecting notice"
        assert mgr.is_showing()
        assert mgr._label is not None
        assert mgr._label.text() == "reconnecting notice"
        # Persistent-only buttons hidden for transient.
        assert mgr._buttons_row is not None
        assert mgr._buttons_row.isHidden()
    finally:
        mgr.close()
    assert mgr.mode is None


def test_transient_auto_dismiss(qapp):
    mgr = ToastManager()
    mgr.show_transient("bye soon", duration_ms=60)
    assert mgr.is_showing()
    QTest.qWait(400)
    assert not mgr.is_showing()
    assert mgr.mode is None
    assert mgr._window is not None
    assert mgr._window.isHidden()
    mgr.close()


def test_persistent_with_actions(qapp):
    mgr = ToastManager()
    try:
        mgr.show_persistent("connection dead")
        assert mgr.mode == "persistent"
        assert mgr.message == "connection dead"
        assert mgr._label is not None
        assert mgr._label.text() == "connection dead"
        buttons = _buttons(mgr)
        assert "Open Settings" in buttons
        assert "Dismiss" in buttons
        assert buttons["Open Settings"].isVisible()
        # Open Settings emits without dismissing the sticky error.
        received = []
        mgr.signals.open_settings.connect(lambda: received.append(True))
        buttons["Open Settings"].click()
        assert received == [True]
        assert mgr.mode == "persistent"
        # Dismiss hides it.
        buttons["Dismiss"].click()
        assert mgr.mode is None
        assert not mgr.is_showing()
    finally:
        mgr.close()


def test_non_activating_flags(qapp):
    mgr = ToastManager()
    try:
        mgr.show_transient("no focus steal")
        assert mgr._window is not None
        flags = mgr._window.windowFlags()
        assert bool(flags & Qt.WindowType.ToolTip)
        assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
        assert bool(flags & Qt.WindowType.FramelessWindowHint)
        assert mgr._window.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        assert mgr._window.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating
        )
    finally:
        mgr.close()


def test_persistent_replaces_transient(qapp):
    mgr = ToastManager()
    try:
        mgr.show_transient("working...")
        assert mgr.mode == "transient"
        mgr.show_persistent("dead")
        assert mgr.mode == "persistent"
        assert mgr.message == "dead"
        assert mgr._dismiss_timer is None or not mgr._dismiss_timer.isActive()
    finally:
        mgr.close()


def test_transient_never_clobbers_persistent(qapp):
    mgr = ToastManager()
    try:
        mgr.show_persistent("dead")
        mgr.show_transient("working...")
        assert mgr.mode == "persistent"
        assert mgr.message == "dead"
        assert mgr._label is not None
        assert mgr._label.text() == "dead"
    finally:
        mgr.close()


def test_toast_positioned_above_capsule(qapp):
    mgr = ToastManager()
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            pytest.skip("no screen in offscreen platform")
        mgr.show_transient("position check")
        assert mgr._window is not None
        geo = screen.availableGeometry()
        # Toast bottom edge must stay above the capsule strip footprint
        # (36px capsule + 30px bottom margin + 12px gap).
        bottom = mgr._window.y() + mgr._window.height()
        assert bottom <= geo.y() + geo.height() - (36 + 30 + 12) + 1
    finally:
        mgr.close()
