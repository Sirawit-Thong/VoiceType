# tests/test_settings_ui.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_settings_window_has_preview_undo_update_widgets(qapp):
    import pathlib
    import tempfile

    from voice_typing.config.settings import SettingsManager
    from voice_typing.ui.settings_window import SettingsWindow
    with tempfile.TemporaryDirectory() as tmp:
        s = SettingsManager(pathlib.Path(tmp) / "s.json")
        s.load()
        s.set("preview_enabled", True)
        s.set("undo_hotkey_vk", 0x5A)
        s.set("update_check_enabled", True)
        w = SettingsWindow(s)
        assert hasattr(w, "_preview_checkbox")
        assert hasattr(w, "_undo_hotkey_combo")
        assert hasattr(w, "_update_check")
        assert w._preview_checkbox.isChecked() is True
        assert w._undo_hotkey_combo.currentData() == 0x5A
        assert w._update_check.isChecked() is True
        w.close()
