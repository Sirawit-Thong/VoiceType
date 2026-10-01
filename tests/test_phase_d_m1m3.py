# tests/test_phase_d_m1m3.py — Phase D reviewer M1-M3 + easy fixes (m1/m5/m6).
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from voice_typing.ui.worker_queue import WorkerQueue


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _phase_d_app():
    from unittest.mock import patch as _patch
    with _patch("voice_typing.app.set_startup"):
        from voice_typing.app import VoiceTypeApp
        return VoiceTypeApp()


# ── M1: cancel resets busy, double shutdown idempotent ────────────────

def test_m1_cancel_resets_busy():
    q = WorkerQueue()
    try:
        q._set_busy(True)
        assert q.busy is True
        q.cancel_all()
        assert q.busy is False
    finally:
        q.shutdown()


def test_m1_cancel_clears_busy_after_enqueue():
    """Enqueue then cancel: busy must clear even though the single/model
    result is suppressed (emits nothing by design)."""
    q = WorkerQueue()
    try:
        with patch(
            "voice_typing.ui.worker_queue.fetch_live_models",
            side_effect=lambda key: (q.cancel_all(), ["models/x"])[1],
        ):
            seen = []
            q.key_tested.connect(lambda k, ok, msg: seen.append(k))
            q.test_key("k1")
            deadline = time.time() + 10.0
            while time.time() < deadline and q.busy:
                QApplication.processEvents()
                time.sleep(0.01)
            QApplication.processEvents()
            # Suppressed result emits nothing, but busy must be clear.
            assert q.busy is False
    finally:
        q.shutdown()


def test_m1_double_shutdown_idempotent():
    q = WorkerQueue()
    q.shutdown()
    assert q.busy is False
    # Second call must not raise; thread stays stopped.
    q.shutdown()
    assert q.busy is False
    assert not q._thread.isRunning()


def test_m1_shutdown_terminates_hung_thread():
    q = WorkerQueue()
    try:
        thread = MagicMock()
        # First isRunning (outer) True, second (post-wait) True -> terminate.
        thread.isRunning.side_effect = [True, True, False]
        thread.wait.return_value = True
        q._thread = thread
        q.shutdown(timeout_ms=10)
        thread.quit.assert_called_once()
        thread.terminate.assert_called_once()
        assert q.busy is False
        # Idempotent second call: no further terminate.
        thread.reset_mock()
        thread.isRunning.return_value = False
        thread.isRunning.side_effect = None
        q.shutdown(timeout_ms=10)
        thread.terminate.assert_not_called()
    finally:
        q._thread = thread  # keep ref stable; real thread never started
        try:
            q._busy = False
        except Exception:
            pass


# ── M2: clear-history confirm Yes/No ───────────────────────────────────

def test_m2_clear_history_yes_clears():
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
            ) as mock_q:
                app._on_clear_history()
            assert mock_q.called
            args = mock_q.call_args
            # Message names the count ("Clear all 2 dictations?").
            assert "2" in str(args)
            assert worker._history == []
            worker._save_history.assert_called_once()
            assert win.history_panel.count() == 0
        finally:
            app._settings_win = None
            win._queue.shutdown()
    finally:
        app._overlay.close()
        app._toast.close()


def test_m2_clear_history_no_keeps():
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
                return_value=QMessageBox.StandardButton.No,
            ):
                app._on_clear_history()
            assert worker._history == ["a", "b"]
            worker._save_history.assert_not_called()
            assert win.history_panel.count() == 2
        finally:
            app._settings_win = None
            win._queue.shutdown()
    finally:
        app._overlay.close()
        app._toast.close()


# ── M3: single set_history per history_changed ─────────────────────────

def test_m3_single_history_forward_per_emit():
    """history_changed emits exactly one set_history (no double forward)."""
    from voice_typing.app import WorkerSignals
    from voice_typing.ui.settings_window import SettingsWindow

    app = _phase_d_app()
    try:
        worker = MagicMock()
        worker._history = ["h1"]
        worker._signals = WorkerSignals()
        app._worker = worker
        # Persistent path as wired by _spawn_worker.
        worker._signals.history_changed.connect(app._on_history_changed)

        probed = {}

        def fake_exec(self):
            orig = self.history_panel.set_history
            calls = []
            probed["calls"] = calls

            def counting(items):
                calls.append(list(items))
                return orig(items)

            self.history_panel.set_history = counting
            worker._signals.history_changed.emit(["h1", "h2", "h3"])
            QApplication.processEvents()
            probed["count"] = len(calls)
            probed["panel_count"] = self.history_panel.count()
            return QDialog.DialogCode.Accepted

        with patch.object(SettingsWindow, "exec", fake_exec):
            app._open_settings()

        assert probed["count"] == 1
        assert probed["panel_count"] == 3
    finally:
        app._overlay.close()
        app._toast.close()


# ── Easy: m1/m5/m6 ─────────────────────────────────────────────────────

def test_easy_no_dead_fetch_import_in_settings_window():
    import voice_typing.ui.settings_window as sw

    assert not hasattr(sw, "fetch_live_models")
    assert "fetch_live_models" not in dir(sw)


def test_easy_save_and_close_accepts(tmp_path):
    from voice_typing.config.settings import SettingsManager
    from voice_typing.ui.settings_window import SettingsWindow

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    try:
        win._save_and_close()
        assert win.result() == QDialog.DialogCode.Accepted
    finally:
        win._queue.shutdown()


def test_easy_ai_keys_tab_renamed_with_compat_alias(tmp_path):
    from voice_typing.config.settings import SettingsManager
    from voice_typing.ui.settings_window import SettingsWindow

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    try:
        assert hasattr(win, "_ai_keys_tab")
        assert hasattr(win, "_gemini_tab")
        assert win._gemini_tab == win._ai_keys_tab
    finally:
        win._queue.shutdown()
