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
