# tests/test_settings_window.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from voice_typing.config.settings import DEFAULT_SETTINGS, SettingsManager
from voice_typing.ui.settings_window import SettingsWindow, _LiveMicTester, _normalize_model


@pytest.fixture(autouse=True)
def _disable_vault_backend(monkeypatch):
    """Force fallback mode so tests ignore any live OS vault."""
    monkeypatch.setenv("VOICETYPE_CREDSTORE_DISABLED", "1")
    from voice_typing.config import credential_store as _cs
    _cs.refresh_backend_cache()
    yield
    _cs.refresh_backend_cache()


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
    assert win._mic_level_bar.value() == 0
    assert win._test_mic_btn.text() == "🎤 Test Mic"


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
    win._copy_to_clipboard.setChecked(True)
    win._lang_combo.setCurrentIndex(1)  # thai
    win._speed_slider.setValue(2)
    win._sensitivity_slider.setValue(15)
    win._api_key.setText("AIzaSyTestKey123")
    win._fast_mode.setChecked(False)
    win._custom_vocab.setText("Python, PySide6, Gemini, Prompt engineering")

    win._save_and_close()

    assert saved_signal_mock.called
    assert mgr.get("mode") == "toggle"
    assert mgr.get("capsule_style") == "dot"
    assert mgr.get("opacity") == pytest.approx(0.80)
    assert mgr.get("start_with_windows") is True
    assert mgr.get("show_status_bar") is False
    assert mgr.get("sound_feedback") is False
    assert mgr.get("copy_to_clipboard") is True
    assert mgr.get("language") == "thai"
    assert mgr.get("typing_speed") == 2
    assert mgr.get("silence_threshold") == pytest.approx(0.015)
    assert mgr.get("api_key") == "AIzaSyTestKey123"
    assert mgr.get("fast_mode") is False
    assert mgr.get("custom_vocabulary") == "Python, PySide6, Gemini, Prompt engineering"


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
    assert "Press a key or mouse button to capture" in win._capture_btn.text()
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


def test_settings_window_mouse_capture_middle_button(settings):
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF

    win = SettingsWindow(settings)
    win._start_key_capture()
    assert win._capturing_key

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handled = win.eventFilter(win, event)
    assert handled is True
    assert not win._capturing_key
    assert win._hotkey_combo.currentData() == 0x04  # VK_MBUTTON


def test_settings_window_mouse_capture_xbutton1(settings):
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF

    win = SettingsWindow(settings)
    win._start_key_capture()
    assert win._capturing_key

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(10, 10),
        Qt.MouseButton.BackButton,
        Qt.MouseButton.BackButton,
        Qt.KeyboardModifier.NoModifier,
    )
    handled = win.eventFilter(win, event)
    assert handled is True
    assert not win._capturing_key
    assert win._hotkey_combo.currentData() == 0x05  # VK_XBUTTON1


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
    win._copy_to_clipboard.setChecked(True)
    win._custom_vocab.setText("Custom Vocab Test")

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "information"):
        win._reset_to_defaults()

    assert win._mode_combo.currentData() == DEFAULT_SETTINGS["mode"]
    assert win._opacity_slider.value() == int(DEFAULT_SETTINGS["opacity"] * 100)
    assert win._opacity_label.text() == f"{int(DEFAULT_SETTINGS['opacity'] * 100)}%"
    assert win._api_key.text() == DEFAULT_SETTINGS["api_key"]
    assert win._copy_to_clipboard.isChecked() == DEFAULT_SETTINGS["copy_to_clipboard"]
    assert win._custom_vocab.text() == DEFAULT_SETTINGS["custom_vocabulary"]


def test_settings_window_test_beep(settings):
    win = SettingsWindow(settings)
    with patch("winsound.Beep", create=True) as mock_beep, \
         patch("threading.Thread") as mock_thread:
        mock_instance = MagicMock()
        mock_thread.return_value = mock_instance
        win._play_test_beep()
        assert mock_thread.called
        assert mock_instance.start.called


def test_settings_window_mic_test_toggle_and_callbacks(settings):
    win = SettingsWindow(settings)
    assert win._test_mic_btn.text() == "🎤 Test Mic"
    assert win._mic_level_bar.value() == 0

    with patch("voice_typing.ui.settings_window._LiveMicTester") as MockTester:
        mock_tester_instance = MagicMock()
        MockTester.return_value = mock_tester_instance
        mock_tester_instance.isRunning.return_value = False

        # Start test
        win._toggle_mic_test()
        assert win._test_mic_btn.text() == "⏹ Stop Test"
        assert win._mic_tester == mock_tester_instance
        assert mock_tester_instance.start.called

        # When level signal changes
        win._mic_level_bar.setValue(55)
        assert win._mic_level_bar.value() == 55

        # Stop test
        mock_tester_instance.isRunning.return_value = True
        win._toggle_mic_test()
        assert mock_tester_instance.stop.called
        assert win._test_mic_btn.text() == "🎤 Test Mic"
        assert win._mic_level_bar.value() == 0
        assert win._mic_tester is None


def test_live_mic_tester_thread():
    tester = _LiveMicTester(device_id=None, duration_sec=0.1)
    levels = []
    tester.level_changed.connect(levels.append)
    finished_called = []
    tester.finished.connect(lambda: finished_called.append(True))

    with patch("sounddevice.InputStream") as mock_stream:
        # Simulate InputStream context manager triggering callback with audio data
        class MockInputStreamCtx:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        def fake_stream(*args, **kwargs):
            cb = kwargs.get("callback")
            if cb:
                fake_audio = np.array([0.5, -0.5, 0.2], dtype=np.float32)
                cb(fake_audio, 3, None, None)
            return MockInputStreamCtx()

        mock_stream.side_effect = fake_stream
        tester.start()
        tester.wait(2000)
        QApplication.processEvents()

        assert len(levels) > 0
        assert levels[0] == 50
        assert len(finished_called) == 1
