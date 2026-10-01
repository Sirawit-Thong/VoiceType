# tests/test_app.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_imports():
    from voice_typing.config.settings import SettingsManager
    from voice_typing.audio.recorder import AudioRecorder
    from voice_typing.speech.engine import TranscriptBuffer
    from voice_typing.windows.text_injector import TextInjector
    from voice_typing.windows.hotkey import HotkeyManager
    from voice_typing.speech.gemini_live import GeminiLiveClient
    assert True


def test_full_flow_mock():
    from voice_typing.config.settings import SettingsManager
    from voice_typing.speech.engine import TranscriptBuffer
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "settings.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        mgr.save()

        buf = TranscriptBuffer()
        buf.add_partial("hello")
        buf.add_partial("hello world")
        result = buf.finalize()
        assert result == "hello world"


def test_stop_recording_on_connection_lost():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.speech.engine import TranscriptBuffer
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._buffer = TranscriptBuffer()
        worker._buffer.add_partial("hello world")
        worker._injector = MagicMock()
        worker._stop_recording_on_connection_lost()
        worker._recorder.stop.assert_called_once()
        worker._injector.inject.assert_called_once_with("hello world")


def test_connection_lost_no_double_stop():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recorder.is_recording = False
        worker._injector = MagicMock()
        worker._stop_recording_on_connection_lost()
        worker._recorder.stop.assert_not_called()
        worker._injector.inject.assert_not_called()


def test_two_utterances_no_doubling():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()
        worker._on_partial("sawasdee")
        worker._on_final("")
        worker._on_partial("phom pen thai")
        worker._on_final("")
        calls = [c.args[0] for c in worker._injector.inject.call_args_list]
        assert calls == ["sawasdee", " phom pen thai"]


def test_no_duplicate_injection_on_repeated_end_of_turn():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()
        worker._on_partial("sawasdee")
        worker._on_final("")
        worker._on_partial("sawasdee")
        worker._on_final("")
        worker._injector.inject.assert_called_once_with("sawasdee")


def test_same_text_after_interval_is_injected_again():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()
        worker._on_partial("hello")
        worker._on_final("")
        worker._last_inject_time -= 10
        worker._on_partial("hello")
        worker._on_final("")
        assert worker._injector.inject.call_count == 2


def test_audio_level_emitted():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import array
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._recording = True
        captured = []
        worker._signals.audio_level.connect(lambda v: captured.append(v))
        chunk = array.array("h", [8000] * 240).tobytes()
        worker._on_audio_chunk(chunk)
        assert len(captured) == 1
        assert isinstance(captured[0], float)
        assert 0.0 <= captured[0] <= 1.0


def test_audio_level_silent_emits_zero():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import array
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._recording = True
        captured = []
        worker._signals.audio_level.connect(lambda v: captured.append(v))
        worker._on_audio_chunk(array.array("h", [0] * 240).tobytes())
        assert captured == [0.0]


def test_history_appends_and_dedupes():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import json
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._inject("hello")
        worker._inject("hello")
        worker._inject("world")
        assert worker._history == ["hello", "world"]
        history_file = Path(tmp) / "history.json"
        assert history_file.exists()
        assert json.loads(history_file.read_text(encoding="utf-8")) == [
            "hello",
            "world",
        ]


def test_history_persisted_and_loaded():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        worker = WorkerThread(mgr)
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._inject("a")
        worker._inject("b")
        worker2 = WorkerThread(mgr)
        worker2._recorder = MagicMock()
        worker2._injector = MagicMock()
        assert worker2._history == ["a", "b"]


def test_re_inject_not_in_history():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._inject("hello")
        worker._re_inject("hello")
        assert worker._history == ["hello"]


def test_reconfigure_hotkey_unregisters_old_and_registers_new():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("hotkey", 0x78)  # F9
        mgr.set("mode", "push_to_talk")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()

        # Initial registration
        worker.reconfigure_hotkey()
        worker._hotkey_mgr.register.assert_called_once_with(
            0x78, worker._on_hotkey, on_release=worker._on_hotkey_release
        )
        worker._hotkey_mgr.unregister.assert_not_called()
        assert worker._current_hotkey_vk == 0x78

        # Reconfigure to F10 (0x79)
        mgr.set("hotkey", 0x79)
        worker.reconfigure_hotkey()
        worker._hotkey_mgr.unregister.assert_called_once_with(0x78)
        worker._hotkey_mgr.register.assert_called_with(
            0x79, worker._on_hotkey, on_release=worker._on_hotkey_release
        )
        assert worker._current_hotkey_vk == 0x79

        # Switch mode to toggle: same hotkey, release callback is None, no unregister called
        mgr.set("mode", "toggle")
        worker.reconfigure_hotkey()
        assert worker._hotkey_mgr.unregister.call_count == 1
        worker._hotkey_mgr.register.assert_called_with(
            0x79, worker._on_hotkey, on_release=None
        )
        assert worker._current_hotkey_vk == 0x79


def test_repeated_utterance_short_debounce_window():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()

        # 1. First injection
        worker._on_partial("hello")
        worker._on_final("")
        assert worker._injector.inject.call_count == 1
        assert worker._injector.inject.call_args[0][0] == "hello"

        # 2. Duplicate within 0.5s is dropped
        worker._on_partial("hello")
        worker._on_final("")
        assert worker._injector.inject.call_count == 1

        # 3. Same text after 0.6s is injected
        worker._last_inject_time -= 0.6
        worker._on_partial("hello")
        worker._on_final("")
        assert worker._injector.inject.call_count == 2

        # 4. Different text within short window is injected immediately
        worker._on_partial("world")
        worker._on_final("")
        assert worker._injector.inject.call_count == 3


def test_worker_update_settings():
    from voice_typing.app import WorkerThread
    from voice_typing.ai.text_processor import TextProcessor
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-123")
        mgr.set("fast_mode", True)
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()

        # Fast mode = True -> no text processor
        worker.update_settings()
        assert worker._processor is None

        # Fast mode = False -> instantiate TextProcessor
        mgr.set("fast_mode", False)
        worker.update_settings()
        assert isinstance(worker._processor, TextProcessor)

        # Empty api key -> processor is None
        mgr.set("api_key", "")
        worker.update_settings()
        assert worker._processor is None

        # Dynamic client disconnect when model/language changes
        mgr.set("api_key", "test-key-123")
        mgr.set("model", "models/gemini-2.0-flash")
        mgr.set("language", "auto")
        worker._client = MagicMock()
        worker._client._api_key = "test-key-123"
        worker._client._model = "models/gemini-2.0-flash"
        worker._current_language = "auto"
        worker._loop = MagicMock()
        worker._loop.is_running.return_value = False

        # Changing language triggers disconnect
        mgr.set("language", "thai")
        worker.update_settings()
        worker._loop.run_until_complete.assert_called_once_with(
            worker._client.disconnect()
        )


def test_app_on_settings_saved():
    from voice_typing.app import VoiceTypeApp
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup") as mock_set_startup:
        app = VoiceTypeApp()
        app._status_bar = MagicMock()
        app._tray = MagicMock()
        app._worker = MagicMock()
        app._worker.isRunning.return_value = True
        app._settings.set("hotkey", 0x79)
        app._settings.set("mode", "toggle")
        app._settings.set("capsule_style", "dot")
        app._settings.set("start_with_windows", True)

        app._on_settings_saved()

        app._status_bar.set_hotkey_name.assert_called_once_with("F10")
        app._status_bar.set_style.assert_called_once_with("dot")
        app._tray.set_mode.assert_called_once_with("toggle")
        app._worker.reconfigure_hotkey.assert_called_once()
        app._worker.update_settings.assert_called_once()
        mock_set_startup.assert_called_once_with(True)


def test_app_tray_event_handlers():
    from voice_typing.app import VoiceTypeApp
    from unittest.mock import MagicMock, patch
    from PySide6.QtWidgets import QMessageBox

    app = VoiceTypeApp()
    app._worker = MagicMock()
    app._worker.isRunning.return_value = True
    app._worker._history = ["line1", "line2"]
    app._tray = MagicMock()

    app._on_language_changed("thai")
    assert app._settings.get("language") == "thai"
    app._worker.update_settings.assert_called_once()

    with patch.object(
        QMessageBox, "question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        app._on_clear_history()
    assert len(app._worker._history) == 0
    app._tray.set_history.assert_called_once_with([])


def test_app_on_test_microphone():
    from voice_typing.app import VoiceTypeApp
    from unittest.mock import MagicMock, patch

    app = VoiceTypeApp()
    with patch("voice_typing.app._MicTester") as mock_mic_tester_cls:
        mock_tester_instance = MagicMock()
        mock_mic_tester_cls.return_value = mock_tester_instance

        app._on_test_microphone()

        mock_mic_tester_cls.assert_called_once_with(
            device_id=app._settings.get("microphone_device_id")
        )
        mock_tester_instance.finished_test.connect.assert_called_once_with(
            app._on_mic_test_result
        )
        mock_tester_instance.start.assert_called_once()


def test_app_on_mic_test_result():
    from voice_typing.app import VoiceTypeApp
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.QMessageBox") as mock_msgbox:
        app = VoiceTypeApp()
        app._on_mic_test_result(True, "Working!")
        mock_msgbox.information.assert_called_once_with(None, "Microphone Test", "Working!")

        mock_msgbox.reset_mock()
        app._on_mic_test_result(False, "Failed!")
        mock_msgbox.warning.assert_called_once_with(None, "Microphone Test", "Failed!")


def test_settings_window_normalize_model():
    from voice_typing.ui.settings_window import _normalize_model
    from voice_typing.speech.gemini_live import MODEL

    assert _normalize_model("gemini-2.0-flash") == "models/gemini-2.0-flash"
    assert _normalize_model("models/gemini-2.0-flash") == "models/gemini-2.0-flash"
    assert _normalize_model("") == MODEL
    assert _normalize_model(None) == MODEL
    assert _normalize_model("   ") == MODEL


def test_settings_window_open_and_save(tmp_path):
    from voice_typing.ui.settings_window import SettingsWindow
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    assert win._mode_combo.count() == 2
    assert win._capsule_style_combo.count() == 2
    win._capsule_style_combo.setCurrentIndex(1)  # "dot"
    win._save_and_close()
    assert mgr.get("capsule_style") == "dot"



def test_worker_thread_stop():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._client = MagicMock()
        worker._loop = MagicMock()
        worker._loop.is_running.return_value = True
        worker._hotkey_mgr = MagicMock()

        worker.stop()

        assert worker._should_stop is True
        assert worker._recording is False
        worker._recorder.stop.assert_called_once()
        worker._client.abort.assert_called_once()
        worker._loop.call_soon_threadsafe.assert_called_once()
        worker._hotkey_mgr.stop.assert_called_once()


def test_app_exit_clean_shutdown():
    from voice_typing.app import VoiceTypeApp, _release_single_instance
    from unittest.mock import MagicMock, patch

    app = VoiceTypeApp()
    app._worker = MagicMock()
    app._worker.isRunning.return_value = True
    app._worker.wait.return_value = True
    app._mic_tester = MagicMock()
    app._mic_tester.isRunning.return_value = True
    app._mic_tester.wait.return_value = True
    app._settings_win = MagicMock()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    app._qapp = MagicMock()

    app._exit()

    app._worker.stop.assert_called_once()
    app._worker.wait.assert_called_once_with(500)
    app._mic_tester.terminate.assert_called_once()
    app._settings_win.close.assert_called_once()
    app._status_bar.close.assert_called_once()
    app._tray.hide.assert_called_once()
    app._qapp.quit.assert_called_once()


def test_app_opacity_propagated_on_settings_saved():
    from voice_typing.app import VoiceTypeApp
    from unittest.mock import MagicMock, patch

    app = VoiceTypeApp()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    app._worker = MagicMock()
    app._worker.isRunning.return_value = True
    app._settings.set('opacity', 0.75)
    app._settings.set('capsule_style', 'pill')

    with patch('voice_typing.app.set_startup'):
        app._on_settings_saved()

    app._status_bar.set_opacity.assert_called_with(0.75)


# ── Reconnect logic tests ────────────────────────────────────────────

def test_save_history_method_exists():
    """WorkerThread must have a _save_history method (was missing → AttributeError)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import json
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._inject("hello")
        # Should not raise AttributeError
        worker._save_history()
        history_file = Path(tmp) / "history.json"
        assert history_file.exists()
        assert json.loads(history_file.read_text(encoding="utf-8")) == ["hello"]


def test_clear_history_persists_empty_list():
    """Clearing history should persist empty list to disk."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import json
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        worker = WorkerThread(mgr)
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._inject("hello")
        worker._inject("world")
        assert len(worker._history) == 2

        # Simulate _on_clear_history logic
        worker._history.clear()
        worker._save_history()

        history_file = Path(tmp) / "history.json"
        assert json.loads(history_file.read_text(encoding="utf-8")) == []


def test_reconnect_all_attempts_fail_returns_false():
    """_reconnect should return False when all attempts fail with RETRY errors."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        # Make connect always fail with RETRY error
        mock_client = MagicMock()
        mock_client.last_error_category = ErrorCategory.RETRY
        mock_client.last_error_reason = "Network error"
        mock_client.connect = MagicMock(side_effect=Exception("connection reset"))

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client):
            with patch.object(worker, "_sleep", return_value=False):
                result = worker._reconnect()

        assert result is False


def test_reconnect_second_attempt_succeeds():
    """_reconnect should return True when second attempt succeeds."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch, AsyncMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        call_count = 0
        def connect_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("connection reset")
            # Second call succeeds (no exception)

        mock_client = MagicMock()
        mock_client.connect = MagicMock(side_effect=connect_side_effect)
        mock_client.last_error_category = None
        mock_client.last_error_reason = ""

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client):
            with patch.object(worker, "_sleep", return_value=False):
                loop = MagicMock()
                with patch("voice_typing.app.asyncio") as mock_asyncio:
                    mock_asyncio.new_event_loop.return_value = loop
                    mock_asyncio.set_event_loop = MagicMock()
                    result = worker._reconnect()

        assert result is True


def test_reconnect_fatal_error_stops_immediately():
    """_reconnect should return False on first FATAL error without further retries."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        mock_client = MagicMock()
        mock_client.last_error_category = ErrorCategory.FATAL
        mock_client.last_error_reason = "API key is invalid"
        mock_client.connect = MagicMock(side_effect=Exception("401 Unauthorized"))

        sleep_calls = []
        def track_sleep(s):
            sleep_calls.append(s)
            return False

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client):
            with patch.object(worker, "_sleep", side_effect=track_sleep):
                result = worker._reconnect()

        assert result is False
        # Should not have waited for subsequent retries
        assert len(sleep_calls) == 1  # Only one sleep before FATAL abort


def test_reconnect_should_stop_returns_false():
    """_reconnect should return False immediately when _should_stop is True."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._should_stop = True  # Signal to stop

        result = worker._reconnect()
        assert result is False


def test_run_fatal_on_initial_connect():
    """WorkerThread.run() should emit error and return on FATAL connect failure."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "bad-key")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        mock_client = MagicMock()
        mock_client.last_error_category = ErrorCategory.FATAL
        mock_client.last_error_reason = "API key is invalid"
        mock_client.is_connected = False
        mock_client.connect = MagicMock(side_effect=Exception("401 Unauthorized"))

        error_messages = []
        worker._signals.error.connect(lambda msg: error_messages.append(msg))

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client):
            worker.run()

        assert any("API key" in msg or "Cannot connect" in msg for msg in error_messages)


# ── Multi-key pool rotation tests ────────────────────────────────────

def test_worker_builds_pool_from_settings():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        worker = WorkerThread(mgr)
        assert worker._key_pool.keys == ["test-key-1", "test-key-2"]
        assert worker._key_pool.current_key == "test-key-1"


def test_worker_pool_legacy_fallback():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-legacy")
        worker = WorkerThread(mgr)
        # load() syncs api_keys=[legacy], so pool picks it up.
        assert worker._key_pool.current_key == "test-key-legacy"


def test_run_rotates_to_second_key_on_quota():
    """First key fails with rotatable 429 → worker tries second key and connects."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        bad = MagicMock()
        bad.last_error_category = ErrorCategory.FATAL
        bad.last_error_reason = "HTTP 429: Quota exceeded"
        bad.is_connected = False
        bad.connect = MagicMock(side_effect=Exception("429 quota exceeded"))

        good = MagicMock()
        good.last_error_category = None
        good.last_error_reason = ""
        good.is_connected = True
        good.connect = AsyncMock(return_value=None)

        def _stop_after_connect(**kwargs):
            worker._should_stop = True
            raise RuntimeError("stop-loop")

        good.receive_transcript = MagicMock(side_effect=_stop_after_connect)

        errors: list[str] = []
        statuses: list[str] = []
        worker._signals.error.connect(errors.append)
        worker._signals.status.connect(statuses.append)

        with patch(
            "voice_typing.app.GeminiLiveClient", side_effect=[bad, good]
        ):
            worker.run()

        assert errors == []
        assert worker._key_pool.current_key == "test-key-2"
        assert any("key" in s and "2/2" in s for s in statuses)


def test_run_aborts_only_when_pool_exhausted():
    """All keys failing with rotatable errors → single FATAL abort error."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        def _bad_client():
            mock_client = MagicMock()
            mock_client.last_error_category = ErrorCategory.FATAL
            mock_client.last_error_reason = "HTTP 429: Quota exceeded"
            mock_client.is_connected = False
            mock_client.connect = MagicMock(side_effect=Exception("429 quota"))
            return mock_client

        errors: list[str] = []
        worker._signals.error.connect(errors.append)

        with patch("voice_typing.app.GeminiLiveClient", side_effect=[_bad_client(), _bad_client()]):
            worker.run()

        assert len(errors) == 1
        assert "Cannot connect" in errors[0]
        assert worker._key_pool.is_exhausted is True


def test_run_nonrotatable_fatal_does_not_rotate():
    """404 model-not-found aborts immediately without consuming the pool."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        mock_client = MagicMock()
        mock_client.last_error_category = ErrorCategory.FATAL
        mock_client.last_error_reason = "HTTP 404: Model not found"
        mock_client.is_connected = False
        mock_client.connect = MagicMock(side_effect=Exception("404 not found"))

        errors: list[str] = []
        worker._signals.error.connect(errors.append)

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client) as factory:
            worker.run()

        assert factory.call_count == 1
        assert len(errors) == 1
        assert worker._key_pool.is_exhausted is False


def test_reconnect_rotates_on_rotatable_fatal():
    """_reconnect tries the next key after a rotatable FATAL failure."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        bad = MagicMock()
        bad.last_error_category = ErrorCategory.FATAL
        bad.last_error_reason = "HTTP 429: Quota exceeded"
        bad.connect = AsyncMock(side_effect=Exception("429 quota"))

        good = MagicMock()
        good.last_error_category = None
        good.last_error_reason = ""
        good.connect = AsyncMock(return_value=None)

        with patch("voice_typing.app.GeminiLiveClient", side_effect=[bad, good]):
            with patch.object(worker, "_sleep", return_value=False):
                result = worker._reconnect()

        assert result is True
        assert worker._key_pool.current_key == "test-key-2"
        assert worker._client is good
        if worker._loop is not None:
            worker._loop.close()
            worker._loop = None


def test_update_settings_resyncs_pool_and_processor_key():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("fast_mode", False)
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker.update_settings()
        assert worker._key_pool.keys == ["test-key-1", "test-key-2"]
        assert worker._processor is not None
        assert worker._processor._api_key == "test-key-1"

        mgr.set_api_keys(["test-key-9"])
        worker.update_settings()
        assert worker._key_pool.keys == ["test-key-9"]
        assert worker._processor._api_key == "test-key-9"


def test_key_status_suffix_masked():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        worker = WorkerThread(mgr)
        suffix = worker._key_status_suffix()
        assert "1/2" in suffix
        assert "test-key-1" not in suffix


# ── Steady-state (mid-stream) FATAL failover ──────────────────────────

def _make_midstream_clients(worker, reason, category):
    """Build (client1, client2) mocks for a mid-stream FATAL test."""
    from unittest.mock import AsyncMock, MagicMock
    from voice_typing.errors import ErrorCategory as _Cat

    cat = category
    client1 = MagicMock()
    client1.last_error_category = None
    client1.last_error_reason = ""
    client1.is_connected = True
    client1.connect = AsyncMock(return_value=None)

    def _fail_receive(*args, **kwargs):
        client1.last_error_category = cat
        client1.last_error_reason = reason
        client1.is_connected = False
        raise Exception(reason)

    client1.receive_transcript = MagicMock(side_effect=_fail_receive)

    client2 = MagicMock()
    client2.last_error_category = None
    client2.last_error_reason = ""
    client2.is_connected = True
    client2.connect = AsyncMock(return_value=None)

    async def _stop_receive(*args, **kwargs):
        worker._should_stop = True
        return None

    client2.receive_transcript = AsyncMock(side_effect=_stop_receive)
    return client1, client2


def test_midstream_rotatable_fatal_fails_over():
    """Mid-stream 429 FATAL rotates to next key and reconnects (no fatal error)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        client1, client2 = _make_midstream_clients(
            worker, "HTTP 429: Quota exceeded", ErrorCategory.FATAL
        )
        errors: list[str] = []
        statuses: list[str] = []
        worker._signals.error.connect(errors.append)
        worker._signals.status.connect(statuses.append)

        with patch(
            "voice_typing.app.GeminiLiveClient", side_effect=[client1, client2]
        ):
            with patch.object(worker, "_sleep", return_value=False):
                worker.run()

        assert worker._key_pool.current_key == "test-key-2"
        assert errors == []
        assert any("next key" in s for s in statuses)


def test_midstream_401_fatal_fails_over():
    """Mid-stream 401 FATAL also rotates (per-key auth failure)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        client1, client2 = _make_midstream_clients(
            worker, "HTTP 401: API key invalid", ErrorCategory.FATAL
        )
        errors: list[str] = []
        worker._signals.error.connect(errors.append)

        with patch(
            "voice_typing.app.GeminiLiveClient", side_effect=[client1, client2]
        ):
            with patch.object(worker, "_sleep", return_value=False):
                worker.run()

        assert worker._key_pool.current_key == "test-key-2"
        assert errors == []


def test_midstream_nonrotatable_fatal_does_not_rotate():
    """Mid-stream 404 FATAL aborts without rotating or reconnecting."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        client1 = MagicMock()
        client1.last_error_category = None
        client1.last_error_reason = ""
        client1.is_connected = True
        client1.connect = AsyncMock(return_value=None)

        def _fail_404(*args, **kwargs):
            client1.last_error_category = ErrorCategory.FATAL
            client1.last_error_reason = "HTTP 404: Model not found"
            client1.is_connected = False
            raise Exception("404 not found")

        client1.receive_transcript = MagicMock(side_effect=_fail_404)

        errors: list[str] = []
        worker._signals.error.connect(errors.append)

        with patch(
            "voice_typing.app.GeminiLiveClient", return_value=client1
        ) as factory:
            with patch.object(worker, "_sleep", return_value=False):
                worker.run()

        assert factory.call_count == 1
        assert len(errors) == 1
        assert "Connection lost" in errors[0]
        assert worker._key_pool.current_key == "test-key-1"
        assert worker._key_pool.is_exhausted is False


def test_midstream_exhausted_single_key_errors_without_reconnect():
    """Mid-stream rotatable FATAL with all keys on cooldown → error + return.

    Covers the is_exhausted branch (no _reconnect call, single error emit).
    """
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        client1 = MagicMock()
        client1.last_error_category = None
        client1.last_error_reason = ""
        client1.is_connected = True
        client1.connect = AsyncMock(return_value=None)

        def _fail_429(*args, **kwargs):
            client1.last_error_category = ErrorCategory.FATAL
            client1.last_error_reason = "HTTP 429: Quota exceeded"
            client1.is_connected = False
            raise Exception("429 quota exceeded")

        client1.receive_transcript = MagicMock(side_effect=_fail_429)

        errors: list[str] = []
        worker._signals.error.connect(errors.append)

        with patch(
            "voice_typing.app.GeminiLiveClient", return_value=client1
        ) as factory:
            with patch.object(worker, "_sleep", return_value=False):
                worker.run()

        assert factory.call_count == 1  # no reconnect attempted
        assert len(errors) == 1
        assert "Connection lost" in errors[0]
        assert worker._key_pool.is_exhausted is True


# ── Gemini 500 5xx policy (5 rounds, queue across reconnect) ─────────

def _make_5xx_client(fail: bool = True):
    """Fake GeminiLiveClient with RETRY 500 reason (fake keys only)."""
    from unittest.mock import AsyncMock, MagicMock
    from voice_typing.errors import ErrorCategory

    mock_client = MagicMock()
    mock_client.last_error_category = ErrorCategory.RETRY
    mock_client.last_error_reason = "HTTP 500: Server error (transient)"
    mock_client.is_connected = (not fail)
    if fail:
        # Sync MagicMock so the failure raises at call time even when
        # asyncio.new_event_loop is mocked (mirrors existing reconnect tests).
        mock_client.connect = MagicMock(
            side_effect=Exception("HTTP 500 Internal Server Error")
        )
    else:
        # Sync success: with a mocked loop run_until_complete() is a no-op.
        mock_client.connect = MagicMock(return_value=None)
    return mock_client


def test_500_midstream_reconnects_on_attempt_4():
    """500 uses 5 rounds (2,4,8,15,30) — success on attempt 4 (old code died at 3)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-fake")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._should_stop = False

        bad1, bad2, bad3 = (_make_5xx_client(True) for _ in range(3))
        good = _make_5xx_client(False)
        statuses: list[str] = []
        worker._signals.status.connect(statuses.append)

        with patch(
            "voice_typing.app.GeminiLiveClient",
            side_effect=[bad1, bad2, bad3, good],
        ) as factory:
            with patch.object(worker, "_sleep", return_value=False):
                loop = MagicMock()
                with patch("voice_typing.app.asyncio") as mock_asyncio:
                    mock_asyncio.new_event_loop.return_value = loop
                    mock_asyncio.set_event_loop = MagicMock()
                    result = worker._reconnect(
                        last_category=ErrorCategory.RETRY,
                        last_reason="HTTP 500: Server error (transient)",
                    )

        assert result is True
        assert factory.call_count == 4
        assert worker._key_pool.current_index == 0
        assert any("/5" in s for s in statuses)
        if worker._loop is not None:
            worker._loop = None


def test_500_exhaustion_uses_five_attempts_no_rotation():
    """5xx exhaustion tries 5 times and never rotates keys."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set_api_keys(["test-key-1", "test-key-2"])
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._should_stop = False
        start_index = worker._key_pool.current_index

        def _bad():
            return _make_5xx_client(True)

        with patch(
            "voice_typing.app.GeminiLiveClient",
            side_effect=[_bad() for _ in range(5)],
        ) as factory:
            with patch.object(worker, "_sleep", return_value=False):
                result = worker._reconnect(
                    last_category=ErrorCategory.RETRY,
                    last_reason="HTTP 500 Internal Server Error",
                )

        assert result is False
        assert factory.call_count == 5
        assert worker._key_pool.current_index == start_index
        assert worker._key_pool.is_exhausted is False
        assert worker._last_reconnect_5xx is True


def test_non_5xx_reconnect_still_three_attempts():
    """Non-5xx RETRY keeps the legacy 3-round policy (backward compat)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-fake")
        worker = WorkerThread(mgr)
        worker._should_stop = False

        mock_client = MagicMock()
        mock_client.last_error_category = ErrorCategory.RETRY
        mock_client.last_error_reason = "Network error: ConnectionRefused"
        mock_client.connect = MagicMock(side_effect=Exception("connection reset"))

        with patch("voice_typing.app.GeminiLiveClient", return_value=mock_client) as factory:
            with patch.object(worker, "_sleep", return_value=False):
                result = worker._reconnect()

        assert result is False
        assert factory.call_count == 3


def test_press_during_reconnect_queues_pending_no_error():
    """Hotkey during reconnect sets pending + status (no error dead-end)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._client = MagicMock()
        worker._client.is_connected = False
        with worker._lock:
            worker._reconnecting = True

        errors: list[str] = []
        statuses: list[str] = []
        worker._signals.error.connect(errors.append)
        worker._signals.status.connect(statuses.append)

        worker._start_recording()

        assert errors == []
        with worker._lock:
            assert worker._pending_record is True
        assert any("Reconnecting" in s for s in statuses)
        assert worker._recorder.start.call_count == 0


def test_reconnect_success_auto_starts_queued_recording():
    """Pending press auto-starts once after reconnect (queue across reconnect)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-fake")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._should_stop = False
        worker._recorder = MagicMock()
        with worker._lock:
            worker._pending_record = True

        good = MagicMock()
        good.last_error_category = None
        good.last_error_reason = ""
        good.is_connected = True
        good.connect = MagicMock(return_value=None)

        started: list[bool] = []
        worker._signals.recording_started.connect(lambda: started.append(True))

        with patch("voice_typing.app.GeminiLiveClient", return_value=good):
            with patch.object(worker, "_sleep", return_value=False):
                loop = MagicMock()
                with patch("voice_typing.app.asyncio") as mock_asyncio:
                    mock_asyncio.new_event_loop.return_value = loop
                    mock_asyncio.set_event_loop = MagicMock()
                    result = worker._reconnect()

        assert result is True
        assert worker._recorder.start.call_count == 1
        assert started == [True]
        with worker._lock:
            assert worker._pending_record is False
        if worker._loop is not None:
            worker._loop = None


def test_5xx_exhaustion_stays_retryable_no_permanent_dead():
    """Mid-stream 500 exhaustion emits Server-busy status (not fatal error)."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from voice_typing.errors import ErrorCategory
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-fake")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._hotkey_mgr = MagicMock()
        worker._hotkey_mgr.registration_failures.return_value = []
        worker._should_stop = False

        client1 = MagicMock()
        client1.last_error_category = None
        client1.last_error_reason = ""
        client1.is_connected = True
        client1.connect = AsyncMock(return_value=None)

        def _fail_500(*args, **kwargs):
            client1.last_error_category = ErrorCategory.RETRY
            client1.last_error_reason = "HTTP 500: Server error (transient)"
            client1.is_connected = False
            raise Exception("HTTP 500 Internal Server Error")

        client1.receive_transcript = MagicMock(side_effect=_fail_500)

        errors: list[str] = []
        statuses: list[str] = []
        worker._signals.error.connect(errors.append)
        worker._signals.status.connect(statuses.append)

        def _fake_reconnect(last_category=None, last_reason=""):
            worker._last_reconnect_5xx = True
            return False

        def _stop_sleep(_s):
            worker._should_stop = True
            return True

        with patch("voice_typing.app.GeminiLiveClient", return_value=client1):
            with patch.object(
                worker, "_reconnect", side_effect=_fake_reconnect
            ):
                with patch.object(worker, "_sleep", side_effect=_stop_sleep):
                    worker.run()

        assert any("Server busy" in s for s in statuses)
        assert not any("could not reconnect" in e for e in errors)
        assert worker._server_busy_retryable is True
        # 500 never rotates keys
        assert worker._key_pool.current_index == 0


def test_status_bar_reconnecting_state_color():
    """StatusBar reconnecting state is distinct amber #fb8c00 (offscreen)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from voice_typing.ui.status_bar import StatusBar

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    bar = StatusBar()
    bar.set_state("reconnecting", "Reconnecting... (attempt 1/5)")
    assert bar._state_color == "#fb8c00"
    bar.set_state("error", "oops")
    assert bar._state == "error-dead"
    assert bar._state_color == "#9aa0a6"


def test_on_status_routes_reconnecting():
    """VoiceTypeApp._on_status shows reconnecting state for reconnect msgs."""
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
        app._status_bar = MagicMock()
        app._tray = MagicMock()
        app._on_status("Reconnecting... (attempt 2/5)")
        app._status_bar.set_state.assert_called_once_with(
            "reconnecting", "Reconnecting... (attempt 2/5)"
        )
        app._status_bar.set_state.reset_mock()
        app._on_status("Reconnected to Gemini Live")
        app._status_bar.set_state.assert_called_once_with(
            "idle", "Reconnected to Gemini Live"
        )


# ── UX Phase A: routing + idle level emit ────────────────────────────

def test_on_error_routes_to_error_dead():
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
        app._status_bar = MagicMock()
        app._tray = MagicMock()
        app._on_error("boom")
        app._status_bar.set_state.assert_called_once_with("error-dead", "boom")


def test_on_status_idle_fallback():
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
        app._status_bar = MagicMock()
        app._tray = MagicMock()
        # 5xx retryable-idle maps to amber reconnecting (not green idle).
        app._on_status("Server busy, ready to retry - press hotkey again")
        app._status_bar.set_state.assert_called_once_with(
            "reconnecting", "Server busy, ready to retry - press hotkey again"
        )
        app._status_bar.set_state.reset_mock()
        app._on_status("Connecting to Gemini Live...")
        app._status_bar.set_state.assert_called_once_with(
            "idle", "Connecting to Gemini Live..."
        )


def test_audio_level_emits_for_chunk_while_disconnected():
    """Level meter emits for each received chunk while audio flows.

    No always-on capture: AudioRecorder only runs while recording, so idle
    normally receives no chunks. This tests the emit-if-chunk path, not a
    live idle preview.
    """
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import array
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._client = None
        worker._loop = None
        worker._recording = False
        captured = []
        worker._signals.audio_level.connect(lambda v: captured.append(v))
        chunk = array.array("h", [8000] * 240).tobytes()
        worker._on_audio_chunk(chunk)
        assert len(captured) == 1
        assert 0.0 <= captured[0] <= 1.0


def test_audio_level_chunk_while_disconnected_does_not_send_audio():
    """Chunk received while disconnected still emits level but never sends."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    import array
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._injector = MagicMock()
        worker._recording = False
        client = MagicMock()
        client.is_connected = False
        worker._client = client
        worker._loop = MagicMock()
        captured = []
        worker._signals.audio_level.connect(lambda v: captured.append(v))
        worker._on_audio_chunk(array.array("h", [8000] * 240).tobytes())
        assert len(captured) == 1
        client.send_audio.assert_not_called()


def test_hotkey_queue_preserved_when_mic_disabled():
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._client = MagicMock()
        worker._client.is_connected = False
        with worker._lock:
            worker._reconnecting = True
        errors: list[str] = []
        worker._signals.error.connect(errors.append)
        worker._start_recording()
        assert errors == []
        with worker._lock:
            assert worker._pending_record is True


# ── M1: _on_status reconnect routing covers every mid-reconnect string ──

def _on_status_state(msg: str) -> str:
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
        app._status_bar = MagicMock()
        app._tray = MagicMock()
        app._on_status(msg)
        return app._status_bar.set_state.call_args[0][0]


def test_on_status_connection_lost_reconnecting():
    assert _on_status_state("Connection lost - reconnecting...") == "reconnecting"


def test_on_status_reconnect_attempt_progress():
    assert _on_status_state("Reconnecting... (attempt 1/5)") == "reconnecting"


def test_on_status_reconnect_attempt_failed_trying_next_key():
    assert (
        _on_status_state("Reconnect attempt 1 of 5 failed - trying next key...")
        == "reconnecting"
    )


def test_on_status_reconnect_attempt_failed_retrying():
    assert (
        _on_status_state("Reconnect attempt 2 of 3 failed - retrying...")
        == "reconnecting"
    )


def test_on_status_key_failed_trying_next_key():
    assert _on_status_state("Key failed, trying next key...") == "reconnecting"


def test_on_status_will_start_automatically():
    assert (
        _on_status_state("Reconnecting — will start automatically...")
        == "reconnecting"
    )


def test_on_status_reconnected_stays_idle():
    assert _on_status_state("Reconnected to Gemini Live") == "idle"


def test_on_status_server_busy_retry_stays_idle():
    # 5xx retryable-idle is amber reconnecting (not green idle).
    assert (
        _on_status_state("Server busy, ready to retry — press hotkey again")
        == "reconnecting"
    )


# ── M3: press-release during reconnect cancels pending (no auto-start) ──

def test_press_release_during_reconnect_cancels_pending():
    """PTT press then release during reconnect clears pending: no auto-start."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import AsyncMock, MagicMock, patch

    with tempfile.TemporaryDirectory() as tmp:
        mgr = SettingsManager(Path(tmp) / "s.json")
        mgr.load()
        mgr.set("api_key", "test-key-fake")
        mgr.set("model", "models/gemini-3.1-flash-live-preview")
        worker = WorkerThread(mgr)
        worker._recorder = MagicMock()
        worker._client = MagicMock()
        worker._client.is_connected = False
        with worker._lock:
            worker._reconnecting = True

        # Press during reconnect queues pending.
        worker._start_recording()
        with worker._lock:
            assert worker._pending_record is True

        # Release (not recording) cancels pending instead of auto-starting.
        worker._on_hotkey_release(0x78)
        with worker._lock:
            assert worker._pending_record is False

        # Reconnect success must NOT auto-start after cancel.
        good = MagicMock()
        good.last_error_category = None
        good.last_error_reason = ""
        good.is_connected = True
        good.connect = MagicMock(return_value=None)
        started: list[bool] = []
        worker._signals.recording_started.connect(lambda: started.append(True))
        with patch("voice_typing.app.GeminiLiveClient", return_value=good):
            with patch.object(worker, "_sleep", return_value=False):
                loop = MagicMock()
                with patch("voice_typing.app.asyncio") as mock_asyncio:
                    mock_asyncio.new_event_loop.return_value = loop
                    mock_asyncio.set_event_loop = MagicMock()
                    assert worker._reconnect() is True
        assert worker._recorder.start.call_count == 0
        assert started == []
        if worker._loop is not None:
            worker._loop = None


def test_stop_clears_pending_record():
    """WorkerThread.stop() clears a queued pending recording."""
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._hotkey_mgr = MagicMock()
        with worker._lock:
            worker._pending_record = True
        worker.stop()
        with worker._lock:
            assert worker._pending_record is False


# ── UX Phase B: toast routing matrix ─────────────────────────────────

def _phase_b_app():
    """VoiceTypeApp with mocked bar/tray but a REAL ToastManager."""
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    assert app._toast.mode is None
    return app


def test_status_reconnect_shows_transient_toast():
    app = _phase_b_app()
    try:
        app._on_status("Reconnecting... (attempt 1/5)")
        app._status_bar.set_state.assert_called_once_with(
            "reconnecting", "Reconnecting... (attempt 1/5)"
        )
        assert app._toast.mode == "transient"
        assert app._toast.message == "Reconnecting... (attempt 1/5)"
    finally:
        app._toast.close()


def test_status_reconnected_hides_toast():
    app = _phase_b_app()
    try:
        app._toast.show_persistent("Cannot connect: bad key")
        assert app._toast.mode == "persistent"
        app._on_status("Reconnected to Gemini Live")
        app._status_bar.set_state.assert_called_once_with(
            "idle", "Reconnected to Gemini Live"
        )
        assert app._toast.mode is None
    finally:
        app._toast.close()


def test_status_idle_does_not_toast():
    app = _phase_b_app()
    try:
        app._on_status("Connecting to Gemini Live...")
        assert app._toast.mode is None
    finally:
        app._toast.close()


def test_status_server_busy_shows_reconnecting_transient():
    # Server-busy retryable maps to amber reconnecting + transient toast
    # (same as other reconnecting states, via shared RECONNECT_HINTS).
    app = _phase_b_app()
    try:
        app._on_status("Server busy, ready to retry — press hotkey again")
        app._status_bar.set_state.assert_called_once_with(
            "reconnecting", "Server busy, ready to retry — press hotkey again"
        )
        assert app._toast.mode == "transient"
    finally:
        app._toast.close()


def test_error_connection_goes_persistent():
    app = _phase_b_app()
    try:
        app._on_error("Cannot connect: HTTP 401 — check your API key and settings")
        app._status_bar.set_state.assert_called_once_with(
            "error-dead",
            "Cannot connect: HTTP 401 — check your API key and settings",
        )
        app._tray.set_status.assert_called_once_with("Error")
        assert app._toast.mode == "persistent"
        assert "Cannot connect" in app._toast.message
    finally:
        app._toast.close()


def test_error_api_key_missing_goes_persistent():
    app = _phase_b_app()
    try:
        app._on_error("No API key configured")
        assert app._toast.mode == "persistent"
    finally:
        app._toast.close()


def test_error_microphone_goes_transient():
    app = _phase_b_app()
    try:
        app._on_error("Failed to start microphone")
        # Transient: amber processing capsule (not error-dead) + amber tray
        # dot via the message itself + transient toast.
        app._status_bar.set_state.assert_called_once_with(
            "processing", "Failed to start microphone"
        )
        app._tray.set_status.assert_called_once_with(
            "Failed to start microphone"
        )
        assert app._toast.mode == "transient"
    finally:
        app._toast.close()


def test_error_injection_goes_transient():
    app = _phase_b_app()
    try:
        app._on_error("Text injection failed — check target application")
        app._status_bar.set_state.assert_called_once_with(
            "processing", "Text injection failed — check target application"
        )
        app._tray.set_status.assert_called_once_with(
            "Text injection failed — check target application"
        )
        assert app._toast.mode == "transient"
    finally:
        app._toast.close()


def test_recording_start_hides_toast():
    app = _phase_b_app()
    try:
        app._settings.set("sound_feedback", False)
        app._toast.show_persistent("Cannot connect: bad key")
        assert app._toast.mode == "persistent"
        app._on_recording_started()
        assert app._toast.mode is None
        app._tray.update_recording_state.assert_called_once_with(True)
    finally:
        app._toast.close()


def test_no_tray_fast_mode_sync():
    """Tray fast-mode UI removed: no syncs, no toggle handler (Phase B)."""
    import pathlib

    text = pathlib.Path("voice_typing/app.py").read_text(encoding="utf-8")
    assert "set_fast_mode" not in text
    assert "_on_fast_mode_toggled" not in text
    assert "fast_mode_toggled" not in text
    app = _phase_b_app()
    try:
        assert not hasattr(app, "_on_fast_mode_toggled")
        # Worker fast logic untouched (settings-driven, not tray-driven).
        assert "fast_mode" in text
    finally:
        app._toast.close()


def test_toast_open_settings_wired():
    """Toast Open Settings action routes to VoiceTypeApp._open_settings."""
    import pathlib

    text = pathlib.Path("voice_typing/app.py").read_text(encoding="utf-8")
    assert "self._toast.signals.open_settings.connect(self._open_settings)" in text
    app = _phase_b_app()
    try:
        received = []
        app._toast.signals.open_settings.connect(lambda: received.append(True))
        app._toast.show_persistent("Cannot connect: bad key")
        assert app._toast._window is not None
        from PySide6.QtWidgets import QPushButton

        btn = next(
            b
            for b in app._toast._window.findChildren(QPushButton)
            if b.text() == "Open Settings"
        )
        btn.click()
        assert received == [True]
    finally:
        app._toast.close()


# ── UX Phase C: overlay geometry/pin/copy/edit wiring ─────────────────

def _phase_c_app():
    """VoiceTypeApp with mocked bar/tray but a REAL overlay (offscreen)."""
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    return app


def test_overlay_settings_defaults_have_geometry_keys(tmp_path):
    from voice_typing.config.settings import SettingsManager, DEFAULT_SETTINGS

    assert DEFAULT_SETTINGS["overlay_x"] is None
    assert DEFAULT_SETTINGS["overlay_y"] is None
    assert DEFAULT_SETTINGS["overlay_width"] == 450
    assert DEFAULT_SETTINGS["overlay_height"] == 200
    assert DEFAULT_SETTINGS["overlay_pinned"] is False
    mgr = SettingsManager(tmp_path / "s.json")
    mgr.load()
    assert mgr.get("overlay_pinned") is False


def test_overlay_geometry_validation_clamps(tmp_path):
    from voice_typing.config.settings import SettingsManager

    mgr = SettingsManager(tmp_path / "s.json")
    mgr.load()
    mgr.set("overlay_width", 5)
    mgr.set("overlay_height", 9999)
    mgr.set("overlay_x", "bad")
    mgr.set("overlay_pinned", "yes")
    mgr.load()  # reload keeps file values; validate on load path
    # Direct validation check via fresh load from file with bad values.
    import json

    bad = mgr.as_dict()
    bad.update(
        {"overlay_width": 5, "overlay_height": 9999, "overlay_x": "bad",
         "overlay_pinned": "yes"}
    )
    (tmp_path / "s.json").write_text(json.dumps(bad), encoding="utf-8")
    mgr2 = SettingsManager(tmp_path / "s.json")
    mgr2.load()
    assert mgr2.get("overlay_width") == 300
    assert mgr2.get("overlay_height") == 600
    assert mgr2.get("overlay_x") is None
    assert mgr2.get("overlay_pinned") is False


def test_overlay_geometry_changed_persists():
    app = _phase_c_app()
    try:
        app._on_overlay_geometry_changed(12, 34, 450, 200)
        assert app._settings.get("overlay_x") == 12
        assert app._settings.get("overlay_y") == 34
        assert app._settings.get("overlay_width") == 450
        assert app._settings.get("overlay_height") == 200
    finally:
        app._overlay.close()
        app._toast.close()


def test_overlay_pin_toggled_persists():
    app = _phase_c_app()
    try:
        app._on_overlay_pin_toggled(True)
        assert app._settings.get("overlay_pinned") is True
        app._on_overlay_pin_toggled(False)
        assert app._settings.get("overlay_pinned") is False
    finally:
        app._overlay.close()
        app._toast.close()


def test_overlay_copy_uses_clipboard():
    # M5: overlay owns the clipboard write; app handler only delegates
    # (single setText via QApplication.clipboard, no duplicate in app).
    from unittest.mock import MagicMock, patch

    from PySide6.QtWidgets import QApplication

    app = _phase_c_app()
    try:
        app._overlay.set_enabled(True)
        app._overlay.add_final("hello copy")
        with patch.object(
            QApplication, "clipboard", return_value=MagicMock()
        ) as mock_clip_fn:
            mock_clip = mock_clip_fn.return_value
            app._on_overlay_copy_clicked()
            mock_clip.setText.assert_called_once_with("hello copy")
    finally:
        app._overlay.close()
        app._toast.close()


def test_overlay_edit_commits_single_inject_no_double():
    from unittest.mock import MagicMock

    app = _phase_c_app()
    try:
        worker = MagicMock()
        worker._inject = MagicMock()
        app._worker = worker
        app._overlay.add_final("stale final")
        app._on_overlay_edit_committed("edited once")
        worker._inject.assert_called_once_with("edited once")
        # Buffer reset prevents a later finalize from re-injecting stale text.
        worker._buffer.reset.assert_called_once()
    finally:
        app._overlay.close()
        app._toast.close()


def test_overlay_edit_empty_ignored():
    from unittest.mock import MagicMock

    app = _phase_c_app()
    try:
        worker = MagicMock()
        app._worker = worker
        app._on_overlay_edit_committed("   ")
        worker._inject.assert_not_called()
    finally:
        app._overlay.close()
        app._toast.close()


def test_settings_saved_reapplies_pin_and_geometry():
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    worker = MagicMock()
    worker.isRunning.return_value = True
    app._worker = worker
    try:
        app._settings.set("overlay_pinned", True)
        app._settings.set("overlay_width", 450)
        app._settings.set("overlay_height", 200)
        with patch("voice_typing.app.set_startup"):
            app._on_settings_saved()
        assert app._overlay.is_pinned is True
    finally:
        app._overlay.close()
        app._toast.close()


def test_restore_geometry_clamped_to_screen():
    from unittest.mock import MagicMock, patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
    app._status_bar = MagicMock()
    app._tray = MagicMock()
    try:
        app._settings.set("overlay_x", 99999)
        app._settings.set("overlay_y", 99999)
        app._settings.set("overlay_width", 450)
        app._settings.set("overlay_height", 200)
        app._restore_overlay_geometry()
        pending = app._overlay._pending_geometry
        assert pending is not None
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            assert pending[0] <= avail.x() + avail.width() - 100
            assert pending[1] <= avail.y() + avail.height() - 50
    finally:
        app._overlay.close()
        app._toast.close()


# ── Phase C reviewer B1: finals reach the overlay via final_received ──


def test_worker_has_final_received_signal():
    from voice_typing.app import WorkerSignals

    assert hasattr(WorkerSignals, "final_received")


def test_on_final_emits_final_received_and_injects_once():
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()
        finals: list[str] = []
        worker._signals.final_received.connect(finals.append)
        worker._on_partial("hello")
        worker._on_final("hello world")
        # Overlay signal carries the raw final text.
        assert finals == ["hello world"]
        # Inject path unchanged — exactly one inject, no double.
        assert worker._injector.inject.call_count == 1


def test_on_final_empty_uses_buffer_text():
    from pathlib import Path
    import tempfile
    from unittest.mock import MagicMock

    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager

    with tempfile.TemporaryDirectory() as tmp:
        worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
        worker._recorder = MagicMock()
        worker._recording = True
        worker._injector = MagicMock()
        finals: list[str] = []
        worker._signals.final_received.connect(finals.append)
        worker._on_partial("sawasdee")
        worker._on_final("")
        assert finals == ["sawasdee"]
        assert worker._injector.inject.call_count == 1


def test_partial_to_final_overlay_segments_and_copy_nonempty():
    # B1 integration: partial -> final -> overlay segments -> copy non-empty.
    from unittest.mock import MagicMock, patch

    from PySide6.QtWidgets import QApplication

    app = _phase_c_app()
    try:
        app._overlay.set_enabled(True)
        from pathlib import Path
        import tempfile

        from voice_typing.app import WorkerThread
        from voice_typing.config.settings import SettingsManager

        with tempfile.TemporaryDirectory() as tmp:
            worker = WorkerThread(SettingsManager(Path(tmp) / "s.json"))
            worker._recorder = MagicMock()
            worker._recording = True
            worker._injector = MagicMock()
            # Wire exactly like VoiceTypeApp._spawn_worker (signal only feeds
            # overlay; inject path unchanged).
            worker._signals.partial_received.connect(app._overlay.add_partial)
            worker._signals.final_received.connect(app._overlay.add_final)
            worker._on_partial("streaming hello")
            assert app._overlay._segments == [("streaming hello", "partial")]
            worker._on_final("hello world")
            assert ("hello world", "final") in app._overlay._segments
            assert not any(k == "partial" for _, k in app._overlay._segments)
            assert worker._injector.inject.call_count == 1
        with patch.object(
            QApplication, "clipboard", return_value=MagicMock()
        ) as mock_clip_fn:
            mock_clip = mock_clip_fn.return_value
            text = app._overlay.copy_to_clipboard()
            assert text != ""
            assert "hello world" in text
            mock_clip.setText.assert_called_once()
    finally:
        app._overlay.close()
        app._toast.close()


# ── UX Phase D: setup wizard + history panel wiring ──────────────────

def _phase_d_app():
    """VoiceTypeApp with real tray/overlay/toast (offscreen)."""
    from unittest.mock import patch

    with patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        app = VoiceTypeApp()
    return app


class _FakeWizard:
    result = 1  # QDialog.DialogCode.Accepted
    _keys = ["wk-1", "wk-2"]

    def __init__(self, *args, **kwargs):
        pass

    def exec(self):
        return self.__class__.result

    def keys(self):
        return list(self.__class__._keys)

    def language(self):
        return "thai"

    def hotkey(self):
        return 0x79

    def microphone_device_id(self):
        return None


def test_run_setup_wizard_saves_multi_keys():
    from unittest.mock import patch

    app = _phase_d_app()
    try:
        # Hermetic: isolate from the developer's real on-disk settings
        # (in-memory only; never persist fake keys to the real file).
        app._settings.set_api_keys([])
        assert app._settings.get_api_keys() == []
        with patch("voice_typing.ui.setup_wizard.SetupWizard", _FakeWizard), \
             patch.object(app._settings, "save"):
            app._run_setup_wizard()
        assert app._settings.get_api_keys() == ["wk-1", "wk-2"]
        assert app._settings.get("api_key") == "wk-1"
        assert app._settings.get("language") == "thai"
        assert app._settings.get("hotkey") == 0x79
        assert app._settings.get("microphone_device_id") is None
    finally:
        app._overlay.close()
        app._toast.close()


def test_run_setup_wizard_skips_when_key_exists():
    from unittest.mock import patch

    app = _phase_d_app()
    try:
        app._settings.set_api_keys(["existing-key"])

        def _boom(*args, **kwargs):
            raise AssertionError("wizard must not open when a key exists")

        with patch("voice_typing.ui.setup_wizard.SetupWizard", _boom):
            app._run_setup_wizard()
        assert app._settings.get_api_keys() == ["existing-key"]
    finally:
        app._overlay.close()
        app._toast.close()


def test_run_setup_wizard_reject_warns():
    from unittest.mock import patch

    app = _phase_d_app()
    try:
        # Hermetic: a real on-disk key would make the wizard skip entirely.
        app._settings.set_api_keys([])
        _FakeWizard.result = 0  # Rejected
        try:
            with patch("voice_typing.ui.setup_wizard.SetupWizard", _FakeWizard), \
                 patch("voice_typing.app.QMessageBox") as mock_msgbox:
                app._run_setup_wizard()
            mock_msgbox.warning.assert_called_once()
            assert app._settings.get_api_keys() == []
        finally:
            _FakeWizard.result = 1
    finally:
        app._overlay.close()
        app._toast.close()


def test_on_history_changed_forwards_to_tray_and_panel():
    from PySide6.QtCore import Qt as _Qt

    from voice_typing.ui.settings_window import SettingsWindow

    app = _phase_d_app()
    try:
        win = SettingsWindow(app._settings)
        app._settings_win = win
        try:
            app._on_history_changed(["a", "b"])
            assert app._tray._history == ["a", "b"]
            assert win.history_panel.count() == 2
            assert win.history_panel._list.item(0).data(
                _Qt.ItemDataRole.UserRole) == "b"
        finally:
            app._settings_win = None
            win._queue.shutdown()
    finally:
        app._overlay.close()
        app._toast.close()


def test_open_settings_wires_history_panel():
    """End-to-end: seed + re-inject + clear flow through the panel."""
    from unittest.mock import MagicMock, patch

    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QDialog, QMessageBox
    from voice_typing.ui.settings_window import SettingsWindow

    app = _phase_d_app()
    try:
        worker = MagicMock()
        worker._history = ["h1", "h2"]
        app._worker = worker
        probed = {}

        def fake_exec(self):
            # The dialog is "open": app._settings_win is still set.
            probed["seeded"] = self.history_panel.count()
            probed["first"] = self.history_panel._list.item(0).data(
                _Qt.ItemDataRole.UserRole)
            self.history_panel._list.setCurrentRow(0)
            self.history_panel._reinject_btn.click()
            self.history_panel._clear_btn.click()
            probed["after_clear"] = self.history_panel.count()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsWindow, "exec", fake_exec), \
             patch.object(
                 QMessageBox, "question",
                 return_value=QMessageBox.StandardButton.Yes,
             ):
            app._open_settings()

        assert probed["seeded"] == 2
        assert probed["first"] == "h2"
        worker._re_inject.assert_called_once_with("h2")
        assert worker._history == []
        worker._save_history.assert_called_once()
        assert app._tray._history == []
        assert probed["after_clear"] == 0
    finally:
        app._overlay.close()
        app._toast.close()


def test_on_clear_history_updates_panel():
    from unittest.mock import MagicMock, patch

    from PySide6.QtWidgets import QMessageBox
    from voice_typing.ui.settings_window import SettingsWindow

    app = _phase_d_app()
    try:
        worker = MagicMock()
        worker._history = ["a", "b"]
        app._worker = worker
        win = SettingsWindow(app._settings)
        app._settings_win = win
        try:
            win.history_panel.set_history(["a", "b"])
            with patch.object(
                QMessageBox, "question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                app._on_clear_history()
            assert worker._history == []
            worker._save_history.assert_called_once()
            assert app._tray._history == []
            assert win.history_panel.count() == 0
        finally:
            app._settings_win = None
            win._queue.shutdown()
    finally:
        app._overlay.close()
        app._toast.close()
