# tests/test_setup_wizard.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from voice_typing.app import VoiceTypeApp


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_wizard_skips_when_provider_configured():
    app = VoiceTypeApp()
    app._settings.set("provider_id", "gemini_live")
    app._settings.set("provider_profiles", {"gemini_live": {"api_key": "k", "model": "m"}})
    with patch("voice_typing.app.QInputDialog") as dlg:
        app._run_setup_wizard()
        dlg.getItem.assert_not_called()
        dlg.getText.assert_not_called()


def test_wizard_saves_chosen_provider_and_key():
    app = VoiceTypeApp()
    app._settings.set("provider_id", "gemini_live")
    app._settings.set("provider_profiles", {})
    app._settings.set("api_key", "")
    app._settings.set("model", "")
    with patch("voice_typing.app.QInputDialog") as dlg:
        dlg.getItem.return_value = ("Groq (batch upload)", True)
        dlg.getText.return_value = ("gsk-fake-test-key", True)
        with patch("voice_typing.app.QMessageBox"):
            app._run_setup_wizard()
    assert app._settings.get("provider_id") == "groq"
    saved = app._settings.get("provider_profiles")["groq"]
    assert saved["api_key"] == "gsk-fake-test-key"
    assert "whisper-large-v3-turbo" in saved["model"]


def test_wizard_cancel_keeps_settings_open():
    app = VoiceTypeApp()
    app._settings.set("provider_id", "gemini_live")
    app._settings.set("provider_profiles", {})
    app._settings.set("api_key", "")
    with patch("voice_typing.app.QInputDialog") as dlg:
        dlg.getItem.return_value = ("Nothing", False)
        with patch("voice_typing.app.QMessageBox") as msg:
            app._run_setup_wizard()
            msg.warning.assert_called_once()
    assert app._settings.get("provider_id") == "gemini_live"
