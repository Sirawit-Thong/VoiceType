# tests/test_settings_window.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from voice_typing.config.settings import DEFAULT_SETTINGS, SettingsManager
from voice_typing.ui.settings_window import SettingsWindow, _normalize_model


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


def test_settings_window_init_and_tabs(settings):
    win = SettingsWindow(settings)
    assert win.windowTitle() == "VoiceType Settings"
    assert win.minimumWidth() >= 550
    assert win.minimumHeight() >= 480

    # Verify slider labels are initialized properly (not empty strings!)
    assert win._opacity_label.text() == f"{int(settings.get('opacity', 0.94) * 100)}%"
    assert win._speed_label.text() == "Instant"
    assert win._sensitivity_label.text() == "Low"


def test_settings_window_slider_interactions(settings):
    win = SettingsWindow(settings)

    # Opacity slider
    win._opacity_slider.setValue(75)
    assert win._opacity_label.text() == "75%"
    win._opacity_slider.setValue(100)
    assert win._opacity_label.text() == "100%"

    # Speed slider
    win._speed_slider.setValue(0)
    assert win._speed_label.text() == "Instant"
    win._speed_slider.setValue(3)
    assert win._speed_label.text() == "3 ms/char"

    # Sensitivity slider
    win._sensitivity_slider.setValue(4)
    assert win._sensitivity_label.text() == "Low"
    win._sensitivity_slider.setValue(10)
    assert win._sensitivity_label.text() == "Medium"
    win._sensitivity_slider.setValue(18)
    assert win._sensitivity_label.text() == "High"


def test_settings_window_save_persists_all_fields(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)

    saved_signal_mock = MagicMock()
    win.saved.connect(saved_signal_mock)

    # Modify all fields
    win._mode_combo.setCurrentIndex(1)  # toggle
    win._capsule_style_combo.setCurrentIndex(1)  # dot
    win._opacity_slider.setValue(80)
    win._start_windows.setChecked(True)
    win._show_status.setChecked(False)
    win._sound_feedback.setChecked(False)
    win._lang_combo.setCurrentIndex(1)  # thai
    win._speed_slider.setValue(2)
    win._sensitivity_slider.setValue(15)
    win._api_key.setText("AIzaSyTestKey123")
    win._fast_mode.setChecked(False)

    win._save_and_close()

    assert saved_signal_mock.called
    assert mgr.get("mode") == "toggle"
    assert mgr.get("capsule_style") == "dot"
    assert mgr.get("opacity") == pytest.approx(0.80)
    assert mgr.get("start_with_windows") is True
    assert mgr.get("show_status_bar") is False
    assert mgr.get("sound_feedback") is False
    assert mgr.get("language") == "thai"
    assert mgr.get("typing_speed") == 2
    assert mgr.get("silence_threshold") == pytest.approx(0.015)
    assert mgr.get("api_key") == "AIzaSyTestKey123"
    assert mgr.get("fast_mode") is False


def test_settings_window_key_capture_success(settings):
    win = SettingsWindow(settings)
    assert not win._capturing_key

    win._start_key_capture()
    assert win._capturing_key
    assert "Listening" in win._capture_btn.text()

    # Simulate key press with native VK (e.g., F10 = 0x79)
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_F10,
        Qt.KeyboardModifier.NoModifier,
        0, 0x79, 0
    )
    win.keyPressEvent(event)

    assert not win._capturing_key
    assert "Press a key to capture" in win._capture_btn.text()
    assert win._hotkey_combo.currentData() == 0x79


def test_settings_window_key_capture_escape_cancels(settings):
    win = SettingsWindow(settings)
    initial_vk = win._hotkey_combo.currentData()

    win._start_key_capture()
    assert win._capturing_key

    # Press Escape key
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )
    win.keyPressEvent(event)

    assert not win._capturing_key
    assert win._hotkey_combo.currentData() == initial_vk


def test_settings_window_key_capture_timeout(settings):
    win = SettingsWindow(settings)
    win._start_key_capture()
    assert win._capturing_key
    win._cancel_key_capture()
    assert not win._capturing_key


def test_settings_window_refresh_mics(settings):
    win = SettingsWindow(settings)
    with patch("voice_typing.ui.settings_window.list_input_devices", return_value=[(1, "USB Mic"), (2, "Headset Mic")]):
        win._refresh_mics()
        assert win._mic_combo.count() == 3
        assert win._mic_combo.itemText(1) == "USB Mic"
        assert win._mic_combo.itemData(1) == 1


def test_settings_window_api_key_test_callbacks(settings):
    win = SettingsWindow(settings)

    # Empty key warning
    win._api_key.setText("")
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._test_api_key()
        mock_warn.assert_called_once()

    # Test success callback
    with patch.object(QMessageBox, "information") as mock_info:
        win._on_api_key_tested(True, "Valid API Key")
        assert "#34a853" in win._api_status.styleSheet()  # Green dot
        assert win._test_key_btn.isEnabled()
        mock_info.assert_called_once()

    # Test fail callback
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._on_api_key_tested(False, "Invalid API Key")
        assert "#ea4335" in win._api_status.styleSheet()  # Red dot
        assert win._test_key_btn.isEnabled()
        mock_warn.assert_called_once()


def test_settings_window_load_models_callbacks(settings):
    win = SettingsWindow(settings)

    # Empty key warning
    win._api_key.setText("")
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._load_models()
        mock_warn.assert_called_once()

    # Success callback
    models_list = ["gemini-2.0-flash", "gemini-2.5-pro"]
    win._on_models_loaded(models_list)
    assert win._load_models_btn.isEnabled()
    assert win._model_combo.count() >= 2
    assert win._model_combo.itemData(0) == "models/gemini-2.0-flash"

    # Failed callback
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._on_models_failed("Network timeout")
        assert win._load_models_btn.isEnabled()
        mock_warn.assert_called_once()


def test_settings_window_reset_to_defaults(settings):
    win = SettingsWindow(settings)

    # Change settings
    win._mode_combo.setCurrentIndex(1)
    win._opacity_slider.setValue(60)
    win._api_key.setText("modified_key")

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "information"):
        win._reset_to_defaults()

    assert win._mode_combo.currentData() == DEFAULT_SETTINGS["mode"]
    assert win._opacity_slider.value() == int(DEFAULT_SETTINGS["opacity"] * 100)
    assert win._opacity_label.text() == f"{int(DEFAULT_SETTINGS['opacity'] * 100)}%"
    assert win._api_key.text() == DEFAULT_SETTINGS["api_key"]
