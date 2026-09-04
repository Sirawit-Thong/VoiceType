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


def _find_action(menu, partial_title):
    for action in menu.actions():
        if action.text() and partial_title in action.text():
            return action
    return None


def test_history_action_emits_open_history(qapp):
    tray = _shown_tray(qapp)
    action = _find_action(tray._menu, "Browse History")
    assert action is not None, "Browse History action not found"
    received = []
    tray.signals.open_history.connect(lambda: received.append(True))
    action.trigger()
    assert received == [True]


def test_update_action_emits_check_update(qapp):
    tray = _shown_tray(qapp)
    action = _find_action(tray._menu, "Check for Updates")
    assert action is not None, "Check for Updates action not found"
    received = []
    tray.signals.check_update.connect(lambda: received.append(True))
    action.trigger()
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


def test_left_click_emits_show_status_bar(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.show_status_bar.connect(lambda: received.append(True))
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert received == [True, True]


def test_set_history_accepts_dict_list(qapp):
    tray = _shown_tray(qapp)
    tray.set_history([
        {"text": "hello", "pinned": False, "created_at": "2026-01-01T00:00:00Z"},
    ])
    action = _find_action(tray._menu, "Browse History")
    assert action is not None
    assert action.isEnabled()
