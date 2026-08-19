# tests/test_app.py
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
