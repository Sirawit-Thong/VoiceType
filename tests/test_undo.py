# tests/test_undo.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _worker(tmp_path):
    from voice_typing.app import WorkerThread
    from voice_typing.config.settings import SettingsManager
    settings = SettingsManager(tmp_path / "s.json")
    settings.load()
    w = WorkerThread.__new__(WorkerThread)
    w._settings = settings
    w._last_injected = ""
    w._undo_available = False
    return w


def test_undo_deletes_post_autospace_length_once(tmp_path):
    w = _worker(tmp_path)
    calls = []
    class FakeInjector:
        def inject(self, text):
            return True
        def delete_chars(self, n):
            calls.append(n)
            return True
    w._injector = FakeInjector()
    w._last_injected = " hello"  # post-auto_space form
    w._undo_available = True
    w._undo_last()
    assert calls == [6]
    w._undo_last()
    assert calls == [6]  # second press no-op


def test_undo_noop_when_disarmed(tmp_path):
    w = _worker(tmp_path)
    class Exploding:
        def delete_chars(self, n):
            raise AssertionError("must not be called")
    w._injector = Exploding()
    w._undo_last()
