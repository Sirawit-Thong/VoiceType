# tests/test_tray.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from voice_typing.ui.tray import TrayIcon


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _shown_tray(qapp):
    tray = TrayIcon()
    try:
        tray.show()
    except Exception:
        tray._menu = QMenu()
        tray._build_menu()
    assert tray._menu is not None
    return tray


def _find_submenu(menu, partial_title):
    for action in menu.actions():
        submenu = action.menu()
        if submenu is not None and partial_title in action.text():
            return submenu
    return None


def _submenu_texts(tray):
    submenu = _find_submenu(tray._menu, "ล่าสุด")
    assert submenu is not None, "Recent (ล่าสุด) submenu not found"
    return [action.text() for action in submenu.actions() if not action.isSeparator() and "Clear History" not in action.text()]


def test_set_history_builds_submenu(qapp):
    tray = _shown_tray(qapp)
    tray.set_history(["a", "b", "c"])
    assert _submenu_texts(tray) == ["c", "b", "a"]


def test_empty_history(qapp):
    tray = _shown_tray(qapp)
    tray.set_history([])
    submenu = _find_submenu(tray._menu, "ล่าสุด")
    assert submenu is not None
    actions = submenu.actions()
    assert len(actions) == 1
    assert not actions[0].isEnabled()
    assert "ว่างเปล่า" in actions[0].text()


def test_click_emits_re_inject(qapp):
    tray = _shown_tray(qapp)
    tray.set_history(["a", "b", "c"])
    submenu = _find_submenu(tray._menu, "ล่าสุด")
    action = next(a for a in submenu.actions() if a.text() == "a")
    received = []
    tray.signals.re_inject.connect(received.append)
    action.trigger()
    assert received == ["a"]


def test_clear_history_emitted(qapp):
    tray = _shown_tray(qapp)
    tray.set_history(["a", "b"])
    submenu = _find_submenu(tray._menu, "ล่าสุด")
    clear_act = next(a for a in submenu.actions() if "Clear History" in a.text())
    received = []
    tray.signals.clear_history.connect(lambda: received.append(True))
    clear_act.trigger()
    assert received == [True]


def test_language_changed_emitted(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.language_changed.connect(received.append)
    tray._set_language("thai")
    assert received == ["thai"]
    assert tray._language == "thai"


def test_fast_mode_toggled_emitted(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.fast_mode_toggled.connect(received.append)
    tray._toggle_fast_mode(False)
    assert received == [False]
    assert tray._fast_mode is False


def test_rebuild_on_second_set_history(qapp):
    tray = _shown_tray(qapp)
    tray.set_history(["a", "b"])
    tray.set_history(["x", "y", "z"])
    texts = _submenu_texts(tray)
    assert texts == ["z", "y", "x"]
    assert "a" not in texts
    assert "b" not in texts


def test_left_click_emits_show_status_bar(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.show_status_bar.connect(lambda: received.append(True))
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert received == [True, True]
