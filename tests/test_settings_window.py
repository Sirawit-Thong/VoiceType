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


def _wait_until(predicate, timeout=10.0):
    """Pump the offscreen event loop until predicate() or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(0.01)
    try:
        return bool(predicate())
    except Exception:
        return False


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
    assert win.minimumWidth() >= 350
    assert win.minimumHeight() >= 300

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

    win._api_key_input.setText("test-key-1")
    win._add_api_key()

    # Test success callback (queue signal shape: key, ok, message)
    with patch.object(QMessageBox, "information") as mock_info:
        win._on_queue_key_tested("test-key-1", True, "Valid API Key")
        assert "#34a853" in win._api_status.styleSheet()  # Green dot
        assert win._test_key_btn.isEnabled()
        mock_info.assert_called_once()

    # Test fail callback
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._on_queue_key_tested("test-key-1", False, "Invalid API Key")
        assert "#ea4335" in win._api_status.styleSheet()  # Red dot
        assert win._test_key_btn.isEnabled()
        mock_warn.assert_called_once()

    assert win._key_status["test-key-1"] == "invalid"
    win._queue.shutdown()


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


# ── Multi-key Gemini tab ─────────────────────────────────────────────

def test_gemini_tab_has_key_list_and_quota_warning(settings):
    win = SettingsWindow(settings)
    assert win._api_keys_list.count() == 0
    assert "share quota" in win._quota_label.text()
    assert "different projects" in win._quota_label.text()
    assert win._add_key_btn is not None
    assert win._remove_key_btn is not None
    assert win._test_all_btn is not None
    # Backward-compat alias for legacy single-field tests.
    assert win._api_key is win._api_key_input


def test_add_and_remove_keys_via_ui(settings):
    win = SettingsWindow(settings)
    win._api_key_input.setText("test-key-1")
    win._add_api_key()
    win._api_key_input.setText("test-key-2")
    win._add_api_key()
    assert win._api_keys_list.count() == 2
    # Display is masked — raw keys never shown.
    assert "test-key-1" not in win._api_keys_list.item(0).text()
    assert win._collect_keys_from_ui() == ["test-key-1", "test-key-2"]

    # Duplicate add is ignored.
    win._api_key_input.setText("test-key-1")
    win._add_api_key()
    assert win._api_keys_list.count() == 2

    # Remove selected.
    win._api_keys_list.setCurrentRow(0)
    win._remove_selected_api_key()
    assert win._collect_keys_from_ui() == ["test-key-2"]


def test_populate_loads_api_keys_with_legacy_fallback(tmp_path):
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("api_key", "test-key-legacy")
    mgr.save()
    mgr2 = SettingsManager(tmp_path / "settings.json")
    mgr2.load()
    win = SettingsWindow(mgr2)
    assert win._collect_keys_from_ui() == ["test-key-legacy"]
    assert win._api_keys_list.count() == 1


def test_save_persists_api_keys_and_mirrors(tmp_path):
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    win._api_key_input.setText("test-key-1")
    win._add_api_key()
    win._api_key_input.setText("test-key-2")
    win._add_api_key()
    win._save_and_close()
    assert mgr.get_api_keys() == ["test-key-1", "test-key-2"]
    assert mgr.get("api_key") == "test-key-1"


def test_save_includes_pending_input_text(tmp_path):
    """Typing a key without pressing Add still saves (legacy compat)."""
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    win._api_key.setText("AIzaSyTestKey123")
    win._save_and_close()
    assert mgr.get("api_key") == "AIzaSyTestKey123"
    assert mgr.get_api_keys() == ["AIzaSyTestKey123"]


def test_test_all_keys_sequential(settings):
    """Test-All runs keys sequentially on the shared WorkerQueue."""
    win = SettingsWindow(settings)
    try:
        win._api_key_input.setText("test-key-1")
        win._add_api_key()
        win._api_key_input.setText("test-key-2")
        win._add_api_key()

        seen_keys = []

        def fake_fetch(key):
            seen_keys.append(key)
            return ["models/gemini-2.0-flash"]

        finished = []
        win._queue.test_all_finished.connect(lambda r: finished.append(list(r)))
        with patch("voice_typing.ui.worker_queue.fetch_live_models", side_effect=fake_fetch), \
             patch.object(QMessageBox, "information") as mock_info, \
             patch.object(QMessageBox, "warning") as mock_warn:
            win._test_all_keys()
            assert _wait_until(lambda: len(finished) == 1)

        assert seen_keys == ["test-key-1", "test-key-2"]
        assert "Valid" in win._api_status.text()
        mock_info.assert_called_once()
        mock_warn.assert_not_called()
        # Per-key dots green + masked indexed labels (raw keys never shown).
        assert win._key_status == {"test-key-1": "valid", "test-key-2": "valid"}
        item0 = win._api_keys_list.item(0)
        assert "test-key-1" not in item0.text()
        assert "(Key 1/2)" in item0.text()
        assert item0.foreground().color().name() == "#34a853"
    finally:
        win._queue.shutdown()


def test_test_all_keys_empty_warns(settings):
    win = SettingsWindow(settings)
    assert win._collect_keys_from_ui() == []
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._test_all_keys()
        mock_warn.assert_called_once()


def test_remove_without_selection_warns_and_keeps_keys(settings):
    win = SettingsWindow(settings)
    win._api_key_input.setText("test-key-1")
    win._add_api_key()
    assert win._api_keys_list.count() == 1
    win._api_keys_list.clearSelection()
    win._api_keys_list.setCurrentRow(-1)
    assert win._api_keys_list.selectedItems() == []
    with patch.object(QMessageBox, "warning") as mock_warn:
        win._remove_selected_api_key()
        mock_warn.assert_called_once()
    assert win._api_keys_list.count() == 1
    assert win._collect_keys_from_ui() == ["test-key-1"]


def test_reset_to_defaults_copies_mutable_list(settings):
    from voice_typing.config.settings import DEFAULT_SETTINGS

    win = SettingsWindow(settings)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes), \
         patch.object(QMessageBox, "information"):
        win._reset_to_defaults()
    assert settings.get("api_keys") is not DEFAULT_SETTINGS["api_keys"]
    settings.get("api_keys").append("fake-injected-key")
    assert "fake-injected-key" not in DEFAULT_SETTINGS["api_keys"]


def test_single_and_all_share_one_queue(settings):
    """Phase D: one WorkerQueue serves single-test, test-all, model loads."""
    win = SettingsWindow(settings)
    try:
        assert win._queue is not None
        assert not hasattr(win, "_key_tester")
        assert not hasattr(win, "_test_all_tester")
        assert not hasattr(win, "_model_loader")
        assert win._queue.busy is False

        finished = []
        win._queue.test_all_finished.connect(lambda r: finished.append(True))
        with patch("voice_typing.ui.worker_queue.fetch_live_models",
                   return_value=["models/x"]), \
             patch.object(QMessageBox, "information"), \
             patch.object(QMessageBox, "warning"):
            win._queue.test_all(["k1"])
            assert _wait_until(lambda: finished)
        assert win._queue.busy is False
    finally:
        win._queue.shutdown()


def test_close_shuts_down_queue_and_resets_buttons(settings):
    """closeEvent cancels the queue, stops its thread, resets buttons."""
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    win._api_key_input.setText("k1")
    win._add_api_key()
    done = []
    win._queue.test_all_finished.connect(lambda r: done.append(True))
    with patch("voice_typing.ui.worker_queue.fetch_live_models",
               return_value=["models/x"]), \
         patch.object(QMessageBox, "information"):
        win._test_all_keys()
        assert _wait_until(lambda: done)
    assert win._queue._thread.isRunning()
    win._set_dirty(False)  # adding a key marks dirty; isolate queue teardown

    win.closeEvent(QCloseEvent())

    assert not win._queue._thread.isRunning()
    assert win._test_all_btn.isEnabled()
    assert win._test_all_btn.text() == "Test All"
    assert win._test_key_btn.isEnabled()
    assert win._test_key_btn.text() == "Test Key"
    assert win._load_models_btn.isEnabled()
    assert win._load_models_btn.text() == "Load models"


def test_close_resets_load_models_button(settings):
    """closeEvent re-enables a stuck Load button even with no queue work."""
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    win._load_models_btn.setEnabled(False)
    win._load_models_btn.setText("Loading...")

    win.closeEvent(QCloseEvent())

    assert win._load_models_btn.isEnabled()
    assert win._load_models_btn.text() == "Load models"


def test_close_aborts_mic_tester_and_resets_ui(settings):
    """closeEvent disconnects mic signals, nulls ref, resets button + bar."""
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    mic = MagicMock()
    mic.isRunning.return_value = True
    win._mic_tester = mic
    win._test_mic_btn.setText("⏹ Stop Test")
    win._mic_level_bar.setValue(55)

    win.closeEvent(QCloseEvent())

    assert win._mic_tester is None
    mic.finished.disconnect.assert_called_once()
    mic.finished_test.disconnect.assert_called_once()
    mic.stop.assert_called_once()
    mic.wait.assert_called_once_with(300)
    assert win._test_mic_btn.text() == "🎤 Test Mic"
    assert win._mic_level_bar.value() == 0


def test_overlay_max_height_round_trip(tmp_path):
    """M4: max-height spinbox binds overlay_max_height (load + save)."""
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("overlay_max_height", 450)
    mgr.save()
    win = SettingsWindow(mgr)
    assert win._overlay_max_height_spin.value() == 450
    win._overlay_max_height_spin.setValue(500)
    win._save_and_close()
    assert mgr.get("overlay_max_height") == 500
    # Reload persists.
    mgr2 = SettingsManager(tmp_path / "settings.json")
    mgr2.load()
    assert mgr2.get("overlay_max_height") == 500


def test_overlay_max_height_clamped_on_load(tmp_path):
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("overlay_max_height", 9999)
    win = SettingsWindow(mgr)
    assert win._overlay_max_height_spin.value() == 600


# ── UX Phase D: sidebar / search ─────────────────────────────────────

def test_sidebar_pages_and_selection(settings):
    win = SettingsWindow(settings)
    try:
        assert win._sidebar.count() == 6
        assert win._stack.count() == 6
        assert win._stack.currentIndex() == 0
        assert win.select_page("Speech")
        assert win._stack.currentIndex() == 2
        assert win.select_page("history")
        assert win._stack.currentIndex() == 4
        assert win.select_page("AI Keys")
        assert win._stack.currentIndex() == 3
        assert not win.select_page("Nope")
    finally:
        win._queue.shutdown()


def test_search_filters_page_titles_only(settings):
    win = SettingsWindow(settings)
    try:
        win._search_box.setText("hot")
        visible = [
            win._sidebar.item(i).text()
            for i in range(win._sidebar.count())
            if not win._sidebar.isRowHidden(i)
        ]
        assert visible == ["Hotkey"]
        # Control-level text must NOT match (page-title only).
        win._search_box.setText("overlay")
        visible = [
            win._sidebar.item(i).text()
            for i in range(win._sidebar.count())
            if not win._sidebar.isRowHidden(i)
        ]
        assert visible == []
        win._search_box.clear()
        assert all(
            not win._sidebar.isRowHidden(i)
            for i in range(win._sidebar.count())
        )
    finally:
        win._queue.shutdown()


# ── UX Phase D: dirty tracking / Ctrl+S / close-confirm ──────────────

def test_dirty_tracking_and_save_shortcut(settings):
    win = SettingsWindow(settings)
    try:
        assert not win.is_dirty
        assert "*" not in win.windowTitle()
        win._mode_combo.setCurrentIndex(1)
        assert win.is_dirty
        assert win.windowTitle().endswith("*")
        assert win._save_shortcut is not None
        # Ctrl+S saves + clears dirty.
        win._save_shortcut.activated.emit()
        assert not win.is_dirty
        assert "*" not in win.windowTitle()
        assert settings.get("mode") == "toggle"
    finally:
        win._queue.shutdown()


def test_close_confirm_cancel_keeps_going(settings):
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    try:
        win._mode_combo.setCurrentIndex(1)
        assert win.is_dirty
        event = QCloseEvent()
        with patch.object(
            QMessageBox, "question",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            win.closeEvent(event)
        assert not event.isAccepted()
        assert win.is_dirty
        assert settings.get("mode") == "push_to_talk"
    finally:
        win._queue.shutdown()


def test_close_confirm_discard_closes_without_saving(settings):
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    win._mode_combo.setCurrentIndex(1)
    event = QCloseEvent()
    with patch.object(
        QMessageBox, "question",
        return_value=QMessageBox.StandardButton.Discard,
    ):
        win.closeEvent(event)
    assert event.isAccepted()
    assert settings.get("mode") == "push_to_talk"
    win._queue.shutdown()


def test_close_confirm_save_persists(settings):
    from PySide6.QtGui import QCloseEvent

    win = SettingsWindow(settings)
    win._mode_combo.setCurrentIndex(1)
    event = QCloseEvent()
    with patch.object(
        QMessageBox, "question",
        return_value=QMessageBox.StandardButton.Save,
    ):
        win.closeEvent(event)
    assert event.isAccepted()
    assert settings.get("mode") == "toggle"
    assert not win.is_dirty
    win._queue.shutdown()


def test_history_selection_does_not_mark_dirty(settings):
    """Dirty = settings controls only (not history selection)."""
    win = SettingsWindow(settings)
    try:
        win.history_panel.set_history(["one", "two"])
        assert win.history_panel.count() == 2
        win.history_panel._list.setCurrentRow(0)
        assert not win.is_dirty
        # Newest-first with full text in UserRole.
        assert win.history_panel._list.item(0).data(
            Qt.ItemDataRole.UserRole) == "two"
    finally:
        win._queue.shutdown()


# ── UX Phase D: per-key dots + queue cancel ──────────────────────────

def test_per_key_dots_masked_indexed(settings):
    win = SettingsWindow(settings)
    try:
        for k in ("alpha-key-1", "beta-key-2"):
            win._api_key_input.setText(k)
            win._add_api_key()
        assert win._key_status == {
            "alpha-key-1": "untested", "beta-key-2": "untested"}
        item = win._api_keys_list.item(0)
        assert "alpha-key-1" not in item.text()
        assert "(Key 1/2)" in item.text()
        assert item.foreground().color().name() == "#9aa0a6"  # gray
        win._set_key_status("alpha-key-1", "testing")
        assert win._api_keys_list.item(0).foreground().color().name() == "#fbbc04"
    finally:
        win._queue.shutdown()


def test_single_key_queue_round_trip(settings):
    win = SettingsWindow(settings)
    try:
        win._api_key_input.setText("solo-key")
        win._add_api_key()
        seen = []
        win._queue.key_tested.connect(lambda k, ok, msg: seen.append((k, ok)))
        with patch("voice_typing.ui.worker_queue.fetch_live_models",
                   return_value=["models/x"]), \
             patch.object(QMessageBox, "information"):
            win._test_api_key()
            assert _wait_until(lambda: seen)
        assert seen == [("solo-key", True)]
        assert win._key_status["solo-key"] == "valid"
        assert "Valid" in win._api_status.text()
    finally:
        win._queue.shutdown()


def test_queue_cancel_emits_partial_results(settings):
    """cancel_all during test-all emits the partial result list."""
    win = SettingsWindow(settings)
    try:
        for k in ("k1", "k2", "k3"):
            win._api_key_input.setText(k)
            win._add_api_key()
        finished = []
        win._queue.test_all_finished.connect(lambda r: finished.append(list(r)))

        def fake_fetch(key):
            if key == "k1":
                win._queue.cancel_all()
            return ["models/x"]

        with patch("voice_typing.ui.worker_queue.fetch_live_models",
                   side_effect=fake_fetch), \
             patch.object(QMessageBox, "warning"), \
             patch.object(QMessageBox, "information"):
            win._test_all_keys()
            assert _wait_until(lambda: finished)
        assert len(finished) == 1
        assert 1 <= len(finished[0]) < 3
        assert finished[0][0][0] == "k1"
        assert finished[0][0][1] is True
    finally:
        win._queue.shutdown()


# ── UX Phase D: history panel + wizard relaunch ──────────────────────

def test_history_panel_copy_reinject_clear():
    from voice_typing.ui.history_panel import HistoryPanel

    panel = HistoryPanel()
    panel.set_history(["first", "second"])
    assert panel.count() == 2
    panel._list.setCurrentRow(0)
    assert panel.selected_text() == "second"
    panel._copy_selected()
    assert QApplication.clipboard().text() == "second"
    got = []
    panel.re_inject.connect(got.append)
    panel._reinject_btn.click()
    assert got == ["second"]
    cleared = []
    panel.clear_history.connect(lambda: cleared.append(True))
    panel._clear_btn.click()
    assert cleared == [True]


def test_history_panel_shows_all_20_newest_first():
    from voice_typing.ui.history_panel import HistoryPanel

    panel = HistoryPanel()
    items = [f"item {i}" for i in range(25)]
    panel.set_history(items)
    assert panel.count() == 20
    assert panel._list.item(0).data(Qt.ItemDataRole.UserRole) == "item 24"
    # Display is truncated for long text; full text stays in UserRole.
    panel.set_history(["x" * 200])
    assert len(panel._list.item(0).text()) < 200
    assert panel._list.item(0).data(Qt.ItemDataRole.UserRole) == "x" * 200


def test_about_page_has_wizard_relaunch(settings):
    from PySide6.QtWidgets import QDialog

    win = SettingsWindow(settings)
    try:
        assert win._wizard_btn is not None
        with patch("voice_typing.ui.setup_wizard.SetupWizard") as MockWiz:
            inst = MockWiz.return_value
            inst.exec.return_value = QDialog.DialogCode.Rejected
            win._open_setup_wizard()
            inst.exec.assert_called_once()
            assert not win.is_dirty
    finally:
        win._queue.shutdown()


def test_wizard_accept_applies_to_ui(settings):
    from PySide6.QtWidgets import QDialog

    win = SettingsWindow(settings)
    try:
        with patch("voice_typing.ui.setup_wizard.SetupWizard") as MockWiz:
            inst = MockWiz.return_value
            inst.exec.return_value = QDialog.DialogCode.Accepted
            inst.keys.return_value = ["wk1"]
            inst.language.return_value = "thai"
            inst.hotkey.return_value = 0x79
            inst.microphone_device_id.return_value = None
            win._open_setup_wizard()
        assert win._collect_keys_from_ui() == ["wk1"]
        assert win._lang_combo.currentIndex() == 1
        assert win._hotkey_combo.currentData() == 0x79
        assert win.is_dirty
    finally:
        win._queue.shutdown()
