# tests/test_preview.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _worker(tmp_path, preview=False):
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    settings = SettingsManager(tmp_path / "s.json")
    settings.load()
    settings.set("preview_enabled", preview)
    w = WorkerThread.__new__(WorkerThread)
    w._settings = settings
    w._last_injected = ""
    w._last_injected_raw = ""
    w._last_inject_time = 0.0
    w._cleanup_provider = None
    w._processor = None
    w._loop = None
    return w


def test_preview_off_injects_directly_no_signal(tmp_path):
    import voice_typing.app as appmod
    w = _worker(tmp_path, preview=False)
    w._signals = appmod.WorkerSignals()
    got = []
    w._signals.preview_requested.connect(lambda s: got.append(s))
    injected = []
    w._injector = type("I", (), {"inject": lambda self, t: injected.append(t) or True})()
    w._history = []
    w._history_texts = lambda: list(w._history)
    w._append_history = lambda t: w._history.append(t)
    w._emit_final_text("hello")
    assert injected == ["hello"]
    assert got == []


def test_preview_on_emits_signal_and_injects_nothing(tmp_path):
    import voice_typing.app as appmod
    w = _worker(tmp_path, preview=True)
    w._signals = appmod.WorkerSignals()
    got = []
    w._signals.preview_requested.connect(lambda s: got.append(s))
    w._injector = type("I", (), {"inject": lambda self, t: (_ for _ in ()).throw(AssertionError("must not inject"))})()
    w._emit_final_text("hello")
    assert got == ["hello"]


def test_dedup_suppresses_repeat_within_half_second(tmp_path):
    import voice_typing.app as appmod
    w = _worker(tmp_path, preview=True)
    w._signals = appmod.WorkerSignals()
    got = []
    w._signals.preview_requested.connect(lambda s: got.append(s))
    w._injector = type("I", (), {"inject": lambda self, t: True})()
    w._emit_final_text("hello")
    w._emit_final_text("hello")  # within 0.5s -> suppressed
    assert got == ["hello"]


import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_preview_dialog_insert_edit_discard(qapp):
    from voice_typing.ui.preview_dialog import PreviewDialog
    d = PreviewDialog()
    d.set_text("hello")
    assert d.current_text() == "hello"
    assert d._text.isReadOnly() is True
    d._on_edit()
    assert d._text.isReadOnly() is False
    d._text.setPlainText("hello edited")
    d._on_insert()
    assert d.take_verdict() == "insert"
    assert d.isHidden()  # offscreen: never shown
    d2 = PreviewDialog()
    d2.set_text("x")
    d2._on_discard()
    assert d2.take_verdict() == "discard"


def test_preview_dialog_last_wins_replaces(qapp):
    from voice_typing.ui.preview_dialog import PreviewDialog
    d = PreviewDialog()
    d.set_text("first")
    d._on_edit()
    d.set_text("second")  # new final replaces, resets to read-only
    assert d.current_text() == "second"
    assert d._text.isReadOnly() is True
