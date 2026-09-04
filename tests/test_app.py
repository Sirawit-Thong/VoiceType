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

        # Dynamic session close when profile/language changes
        mgr.set("api_key", "test-key-123")
        mgr.set("provider_id", "gemini_live")
        mgr.set("provider_profiles", {"gemini_live": {"api_key": "test-key-123", "model": "models/gemini-2.0-flash"}})
        mgr.set("language", "auto")
        worker._provider = MagicMock()
        worker._client = worker._provider
        worker._profile = worker._snapshot_profile()
        worker._current_language = "auto"
        worker._loop = MagicMock()
        worker._loop.is_running.return_value = False

        # Changing language triggers session close
        mgr.set("language", "thai")
        worker.update_settings()
        worker._loop.run_until_complete.assert_called_once_with(
            worker._provider.close()
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

    app._exit(force_exit=False)

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
