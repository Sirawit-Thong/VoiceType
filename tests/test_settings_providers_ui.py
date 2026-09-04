# tests/test_settings_providers_ui.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox

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


def test_provider_selector_lists_all_presets_in_order(settings):
    win = SettingsWindow(settings)
    ids = [win._provider_combo.itemData(i) for i in range(win._provider_combo.count())]
    assert ids == ["gemini_live", "openai_realtime", "groq", "deepgram", "openai_compatible", "freellm"]


def test_groq_selection_shows_preset_defaults_and_marks_unavailable(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("groq"))
    assert "groq.com" in win._base_url.text()
    assert "whisper" in win._model_combo.currentText()
    assert "Unavailable" in win._availability_label.text()


def test_gemini_ready_when_key_entered(settings):
    win = SettingsWindow(settings)
    assert win._provider_combo.currentData() == "gemini_live"
    win._api_key.setText("AIzaFakeTestKey0123456789abcdef")
    win._update_availability()
    assert win._availability_label.text() == "Ready for dictation"


def test_gemini_hides_endpoint_rows(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("gemini_live"))
    assert win._base_url.isHidden()
    assert win._transcription_path.isHidden()
    assert win._send_bearer.isHidden()
    assert win._skip_tls.isHidden()
    assert win._stt_mode_combo.isHidden()


def test_openai_realtime_shows_stt_mode_only(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("openai_realtime"))
    assert not win._stt_mode_combo.isHidden()
    assert win._base_url.isHidden()
    assert win._skip_tls.isHidden()


def test_compatible_shows_endpoint_rows(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("openai_compatible"))
    assert not win._base_url.isHidden()
    assert not win._transcription_path.isHidden()
    assert not win._send_bearer.isHidden()
    assert not win._skip_tls.isHidden()
    assert win._base_url.isEnabled()


def test_load_models_disabled_without_listing_capability(settings):
    win = SettingsWindow(settings)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("groq"))
    assert not win._load_models_btn.isEnabled()
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("gemini_live"))
    assert win._load_models_btn.isEnabled()


def test_save_round_trips_compatible_profile(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("openai_compatible"))
    win._base_url.setText("http://localhost:1234/v1")
    win._model_combo.setCurrentText("whisper-large")
    win._save_and_close()
    assert mgr.get("provider_id") == "openai_compatible"
    saved = mgr.get("provider_profiles")["openai_compatible"]
    assert saved["base_url"] == "http://localhost:1234/v1"
    assert saved["model"] == "whisper-large"
    win2 = SettingsWindow(mgr)
    assert win2._provider_combo.currentData() == "openai_compatible"
    assert win2._base_url.text() == "http://localhost:1234/v1"


def test_save_mirrors_gemini_legacy_keys(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    win._provider_combo.setCurrentIndex(win._provider_combo.findData("gemini_live"))
    win._api_key.setText("AIzaFakeMirrorKey0123456789abcdef")
    win._save_and_close()
    assert mgr.get("api_key") == "AIzaFakeMirrorKey0123456789abcdef"
    assert mgr.get("provider_profiles")["gemini_live"]["api_key"] == "AIzaFakeMirrorKey0123456789abcdef"


def test_model_failure_redacts_key(settings):
    win = SettingsWindow(settings)
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._on_models_failed("boom with key AIzaFakeTestKey0123456789abcdef")
    shown = mock_warn.call_args.args[2]
    assert "AIzaFakeTestKey0123456789abcdef" not in shown
