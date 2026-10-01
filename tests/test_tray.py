# tests/test_tray.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from voice_typing.ui.tray import TrayIcon, TraySignals, status_dot_color


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


def _find_action(menu, partial_title):
    for action in menu.actions():
        if action.menu() is None and partial_title in action.text():
            return action
    return None


def _top_level_texts(tray):
    return [a.text() for a in tray._menu.actions() if not a.isSeparator()]


def test_no_recent_submenu(qapp):
    """Phase D: Recent submenu removed; history lives in Settings."""
    tray = _shown_tray(qapp)
    assert _find_submenu(tray._menu, "Recent") is None
    assert not hasattr(tray, "_recent_menu")
    assert not hasattr(tray, "_rebuild_recent_menu")
    assert not hasattr(tray, "_on_recent_insert")
    assert not hasattr(tray, "_copy_recent")


def test_open_history_in_settings_entry(qapp):
    tray = _shown_tray(qapp)
    act = _find_action(tray._menu, "Open History in Settings")
    assert act is not None
    received = []
    tray.signals.open_history.connect(lambda: received.append(True))
    act.trigger()
    assert received == [True]


def test_set_history_shim_stores_without_menu(qapp):
    """Phase D: set_history is a no-op shim (stores only, no rebuild)."""
    tray = _shown_tray(qapp)
    actions_before = list(tray._menu.actions())
    tray.set_history(["a", "b", "c"])
    assert tray._history == ["a", "b", "c"]
    assert list(tray._menu.actions()) == actions_before
    assert _find_submenu(tray._menu, "Recent") is None


def test_set_history_shim_keeps_latest(qapp):
    tray = _shown_tray(qapp)
    tray.set_history(["a", "b"])
    tray.set_history(["x", "y", "z"])
    assert tray._history == ["x", "y", "z"]


def test_deprecated_history_signals_never_emitted(qapp):
    """clear_history / re_inject retained as no-op signals; UI never emits."""
    assert hasattr(TraySignals, "clear_history")
    assert hasattr(TraySignals, "re_inject")
    tray = _shown_tray(qapp)
    assert _find_action(tray._menu, "Clear History") is None
    assert "Clear History" not in _top_level_texts(tray)


def test_language_changed_emitted(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.language_changed.connect(received.append)
    tray._set_language("thai")
    assert received == ["thai"]
    assert tray._language == "thai"


def test_menu_order_and_no_fast_mode(qapp):
    tray = _shown_tray(qapp)
    texts = _top_level_texts(tray)
    assert texts[0].startswith("●")
    assert texts[1] == "Start Recording"
    assert texts[2] == "Mode"
    assert "Language" in texts[3]
    assert texts[4] == "Open History in Settings"
    assert texts[5] == "Settings"
    assert texts[6] == "Test Microphone"
    assert texts[7] == "Exit"
    assert not any("Fast Mode" in t for t in texts)
    assert not any("Recent" in t for t in texts)


def test_fast_mode_signal_deprecated_not_emitted(qapp):
    # Signal retained for backward compatibility; UI + emit path removed.
    assert hasattr(TraySignals, "fast_mode_toggled")
    tray = _shown_tray(qapp)
    assert not hasattr(tray, "_toggle_fast_mode")
    assert not hasattr(tray, "set_fast_mode")
    assert not hasattr(tray, "_fast_mode")


def test_set_status_updates_dot_row_only(qapp):
    tray = _shown_tray(qapp)
    status_before = tray._status_action
    start_stop_before = tray._start_stop_action
    actions_before = list(tray._menu.actions())
    tray.set_status("Recording...")
    assert tray._status_action is status_before
    assert tray._start_stop_action is start_stop_before
    assert list(tray._menu.actions()) == actions_before
    assert tray._status_action.text() == "● Recording"


def test_status_dot_mapping(qapp):
    assert status_dot_color("Ready") == "#34a853"
    assert status_dot_color("Recording...") == "#34a853"
    assert status_dot_color("Reconnecting... (attempt 1/5)") == "#fb8c00"
    assert status_dot_color("Connection lost - reconnecting...") == "#fb8c00"
    assert status_dot_color("Error") == "#9aa0a6"
    # 5xx retryable-idle maps to amber (not green).
    assert status_dot_color("Server busy, ready to retry — press hotkey again") == "#fb8c00"
    # Transient mic/inject nudges map to amber (not gray).
    assert status_dot_color("Failed to start microphone") == "#fb8c00"
    assert status_dot_color("Text injection failed — check target application") == "#fb8c00"
    # Narrowed "attempt " hint: real reconnect strings still match.
    assert status_dot_color("Reconnect attempt 1 of 5 failed - trying next key...") == "#fb8c00"
    tray = _shown_tray(qapp)
    tray.set_status("Reconnecting... (attempt 1/5)")
    assert tray._status_dot_color == "#fb8c00"
    tray.set_status("Error")
    assert tray._status_dot_color == "#9aa0a6"
    tray.set_status("Ready")
    assert tray._status_dot_color == "#34a853"


def test_update_recording_state_toggles_start_stop(qapp):
    tray = _shown_tray(qapp)
    action_before = tray._start_stop_action
    tray.update_recording_state(True)
    assert tray._start_stop_action is action_before
    assert tray._start_stop_action.text() == "Stop Recording"
    assert tray._status_action.text() == "● Recording"
    tray.update_recording_state(False)
    assert tray._start_stop_action is action_before
    assert tray._start_stop_action.text() == "Start Recording"


def test_left_click_emits_show_status_bar(qapp):
    tray = _shown_tray(qapp)
    received = []
    tray.signals.show_status_bar.connect(lambda: received.append(True))
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
    assert received == [True, True]


def test_tray_uses_theme_token_for_fallback_icon():
    import pathlib

    from voice_typing.ui import _theme as theme

    text = pathlib.Path("voice_typing/ui/tray.py").read_text(encoding="utf-8")
    assert "COLOR_TRAY_FALLBACK_BLUE" in text
    assert theme.COLOR_TRAY_FALLBACK_BLUE == "#1a73e8"
    assert "#1a73e8" not in text
