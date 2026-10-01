# voice_typing/ui/worker_queue.py
"""UX Phase D: single background worker for API-key tests + model loads.

One persistent ``QThread`` hosts a ``_QueueWorker`` QObject; all network
I/O (``fetch_live_models``) runs there so the settings UI never blocks.
Callers enqueue work from the GUI thread:

- :meth:`WorkerQueue.test_key` — test a single key.
- :meth:`WorkerQueue.test_all` — test keys sequentially, one result list.
- :meth:`WorkerQueue.load_models` — fetch the model list for a key.
- :meth:`WorkerQueue.cancel_all` — cancel an in-flight ``test_all`` loop
  (checked between keys; partial results are still emitted).
- :meth:`WorkerQueue.shutdown` — cancel + disconnect + wait (close-safe).

Signals (all delivered on the GUI thread)::

- ``key_tested(key, ok, message)``
- ``test_all_finished(results)`` — ``results`` is
  ``list[tuple[key, ok, message]]`` (partial list when cancelled).
- ``models_loaded(models)``
- ``models_failed(reason)``

Decisions (Phase D, pre-approved):
- Cancel suppresses a pending single-test/model result; ``test_all``
  always emits (possibly partial) results so the UI can update per-key
  dots deterministically.
- ``cancel_all()`` clears ``busy`` immediately (under lock) so the
  suppressed single/model path (which emits nothing by design) can never
  leave the UI stuck busy; ``test_all`` also clears via its result signal.
- Shutdown teardown: ``quit()`` + ``wait(timeout)``; if the thread is
  still running, log an error and ``terminate()`` as a last resort then
  wait briefly again. Terminate is chosen over leaking a hung thread on
  close (close-safe > graceful when the worker is stuck in network I/O).
- Masked logging only (``KeyPool.mask``) — raw key material never hits
  logs. The worker never shows ``QMessageBox`` (UI layer owns dialogs).
- The thread starts lazily on first request so merely constructing a
  settings window never spawns a thread; callers must ``close()`` the
  owning dialog (``closeEvent`` calls ``shutdown()``).
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from voice_typing.speech.gemini_live import fetch_live_models
from voice_typing.speech.key_pool import KeyPool

log = logging.getLogger(__name__)


class _QueueWorker(QObject):
    """Lives on the worker thread; performs blocking network calls."""

    key_result = Signal(str, bool, str)
    all_result = Signal(list)
    models_ok = Signal(list)
    models_err = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()

    @Slot()
    def request_cancel(self) -> None:
        self._cancel.set()

    @Slot(str)
    def do_test_key(self, key: str) -> None:
        self._cancel.clear()
        log.info("WorkerQueue: testing key %s", KeyPool.mask(key))
        try:
            models = fetch_live_models(key)
        except Exception as exc:
            log.warning("WorkerQueue: key %s test failed", KeyPool.mask(key))
            if not self._cancel.is_set():
                self.key_result.emit(key, False, f"API Key test failed:\n{exc}")
            return
        if self._cancel.is_set():
            return
        if models:
            self.key_result.emit(
                key, True,
                f"API Key is valid! Connected to Gemini API ({len(models)} models available).",
            )
        else:
            self.key_result.emit(key, False, "API Key test returned no models.")
        log.info("WorkerQueue: key %s tested (%d models)", KeyPool.mask(key), len(models))

    @Slot(list)
    def do_test_all(self, keys: list) -> None:
        self._cancel.clear()
        order = [k for k in (keys or []) if isinstance(k, str)]
        log.info("WorkerQueue: testing %d key(s)", len(order))
        results: list[tuple[str, bool, str]] = []
        for key in order:
            if self._cancel.is_set():
                log.info(
                    "WorkerQueue: test-all cancelled after %d/%d",
                    len(results), len(order),
                )
                break
            try:
                models = fetch_live_models(key)
            except Exception as exc:
                results.append((key, False, f"API Key test failed:\n{exc}"))
                log.info("WorkerQueue: key %s -> FAIL (%d/%d)",
                         KeyPool.mask(key), len(results), len(order))
                continue
            if models:
                results.append(
                    (key, True,
                     f"API Key is valid! Connected to Gemini API ({len(models)} models available).")
                )
            else:
                results.append((key, False, "API Key test returned no models."))
            log.info("WorkerQueue: key %s -> %s (%d/%d)",
                     KeyPool.mask(key), "OK" if results[-1][1] else "FAIL",
                     len(results), len(order))
        self.all_result.emit(results)

    @Slot(str)
    def do_load_models(self, key: str) -> None:
        self._cancel.clear()
        log.info("WorkerQueue: loading models for key %s", KeyPool.mask(key))
        try:
            models = fetch_live_models(key)
        except Exception as exc:
            log.warning("WorkerQueue: load models failed for key %s", KeyPool.mask(key))
            if not self._cancel.is_set():
                self.models_err.emit(str(exc))
            return
        if self._cancel.is_set():
            return
        log.info("WorkerQueue: loaded %d model(s) for key %s", len(models), KeyPool.mask(key))
        self.models_ok.emit(list(models))


class WorkerQueue(QObject):
    """GUI-thread façade over a single background worker thread."""

    key_tested = Signal(str, bool, str)
    test_all_finished = Signal(list)
    models_loaded = Signal(list)
    models_failed = Signal(str)

    _req_test_key = Signal(str)
    _req_test_all = Signal(list)
    _req_load_models = Signal(str)
    _req_cancel = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._worker = _QueueWorker()
        self._worker.moveToThread(self._thread)
        self._req_test_key.connect(self._worker.do_test_key)
        self._req_test_all.connect(self._worker.do_test_all)
        self._req_load_models.connect(self._worker.do_load_models)
        self._req_cancel.connect(self._worker.request_cancel)
        self._worker.key_result.connect(self.key_tested)
        self._worker.all_result.connect(self.test_all_finished)
        self._worker.models_ok.connect(self.models_loaded)
        self._worker.models_err.connect(self.models_failed)
        self._busy = False
        self._busy_lock = threading.Lock()
        self.key_tested.connect(lambda *a: self._set_busy(False))
        self.test_all_finished.connect(lambda *a: self._set_busy(False))
        self.models_loaded.connect(lambda *a: self._set_busy(False))
        self.models_failed.connect(lambda *a: self._set_busy(False))
        try:
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self.shutdown)
        except Exception:
            pass

    # -- state ---------------------------------------------------------
    @property
    def busy(self) -> bool:
        with self._busy_lock:
            return self._busy

    def _set_busy(self, value: bool) -> None:
        with self._busy_lock:
            self._busy = bool(value)

    def _ensure_started(self) -> None:
        if not self._thread.isRunning():
            self._thread.start()

    # -- requests (GUI thread) ------------------------------------------
    def test_key(self, key: str) -> None:
        log.info("WorkerQueue: enqueue test key %s", KeyPool.mask(key))
        self._ensure_started()
        self._set_busy(True)
        self._req_test_key.emit(key)

    def test_all(self, keys: list[str]) -> None:
        keys = list(keys or [])
        log.info("WorkerQueue: enqueue test-all (%d key(s))", len(keys))
        if not keys:
            self.test_all_finished.emit([])
            return
        self._ensure_started()
        self._set_busy(True)
        self._req_test_all.emit(keys)

    def load_models(self, key: str) -> None:
        log.info("WorkerQueue: enqueue load models for key %s", KeyPool.mask(key))
        self._ensure_started()
        self._set_busy(True)
        self._req_load_models.emit(key)

    def cancel_all(self) -> None:
        """Ask the worker to stop at the next cancellation checkpoint."""
        try:
            self._req_cancel.emit()
        except Exception:
            pass
        # Suppressed single/model results emit nothing by design, so clear
        # busy here (under lock) — otherwise the UI would stay stuck busy.
        self._set_busy(False)

    def shutdown(self, timeout_ms: int = 2000) -> None:
        """Close-safe teardown: cancel + disconnect + wait."""
        try:
            self.cancel_all()
        except Exception:
            pass
        for signal, slot in (
            (self._req_test_key, self._worker.do_test_key),
            (self._req_test_all, self._worker.do_test_all),
            (self._req_load_models, self._worker.do_load_models),
            (self._req_cancel, self._worker.request_cancel),
            (self._worker.key_result, self.key_tested),
            (self._worker.all_result, self.test_all_finished),
            (self._worker.models_ok, self.models_loaded),
            (self._worker.models_err, self.models_failed),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
            except Exception:
                pass
        try:
            if self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(timeout_ms)
                if self._thread.isRunning():
                    # Last resort: the worker may be stuck in blocking
                    # network I/O that ignores quit(). Terminate rather
                    # than leak a hung thread past close (close-safe).
                    log.error("WorkerQueue: thread hung, terminating (last resort)")
                    self._thread.terminate()
                    self._thread.wait(500)
        except Exception:
            pass
        self._set_busy(False)

    def __del__(self) -> None:  # last resort; closeEvent is the real path
        try:
            self.shutdown(timeout_ms=500)
        except Exception:
            pass
