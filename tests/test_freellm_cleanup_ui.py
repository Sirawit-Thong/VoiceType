# tests/test_freellm_cleanup_ui.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from voice_typing.config.settings import SettingsManager
from voice_typing.ui.settings_window import SettingsWindow


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def settings(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    return mgr


def test_freellm_empty_endpoint_is_unavailable(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("freellm"))
    assert "Unavailable" in win._availability_label.text()
    assert "Base URL" in win._availability_label.text()


def test_freellm_configured_endpoint_is_ready(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("freellm"))
    win._base_url.setText("http://localhost:1234/v1")
    win._model_combo.setCurrentText("local-model")
    win._update_availability()
    assert win._availability_label.text() == "Ready for dictation"


def test_unchecking_fast_mode_enables_cleanup_on_save(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("groq"))
    win._api_key.setText("gsk-fake-test-key-0123456789abcdef")
    win._fast_mode.setChecked(False)
    win._save_and_close()
    assert mgr.get("text_cleanup") == {"enabled": True, "provider_id": "groq"}


def test_cleanup_enabled_unchecks_fast_mode_on_load(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("text_cleanup", {"enabled": True, "provider_id": "gemini_live"})
    mgr.save()
    win = SettingsWindow(mgr)
    assert win._fast_mode.isChecked() is False
