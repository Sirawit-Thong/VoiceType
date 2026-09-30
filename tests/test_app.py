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
    from unittest.mock import MagicMock

    app = VoiceTypeApp()
    app._worker = MagicMock()
    app._worker.isRunning.return_value = True
    app._worker._history = ["line1", "line2"]
    app._tray = MagicMock()

    app._on_language_changed("thai")
    assert app._settings.get("language") == "thai"
    app._worker.update_settings.assert_called_once()

    app._worker.update_settings.reset_mock()
    app._on_fast_mode_toggled(False)
    assert app._settings.get("fast_mode") is False
    app._worker.update_settings.assert_called_once()

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
    """StatusBar reconnecting state is yellow #fbbc04 (offscreen)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from voice_typing.ui.status_bar import StatusBar

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    bar = StatusBar()
    bar.set_state("reconnecting", "Reconnecting... (attempt 1/5)")
    assert bar._state_color == "#fbbc04"
    bar.set_state("error", "oops")
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
            "ready", "Reconnected to Gemini Live"
        )
