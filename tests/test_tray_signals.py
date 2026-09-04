# tests/test_tray_signals.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_tray_signals_has_open_history_and_check_update():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    from voice_typing.ui.tray import TraySignals
    sig = TraySignals()
    assert hasattr(sig, "open_history")
    assert hasattr(sig, "check_update")


def test_tray_menu_builds_with_new_actions():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    from voice_typing.ui.tray import TrayIcon
    t = TrayIcon()
    t.show()
    t.set_status("Ready")
    t.set_history([{"text": "hi", "pinned": False, "created_at": "2026-01-01T00:00:00Z"}])
    assert hasattr(t.signals, "open_history")
    assert hasattr(t.signals, "check_update")
    t.hide()
