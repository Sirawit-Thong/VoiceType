# voice_typing/app.py
from __future__ import annotations

import asyncio
import ctypes
import json
import math
import sys
import threading
import time
import winsound
from array import array
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from voice_typing.ai.text_processor import TextProcessor
from voice_typing.audio.recorder import AudioRecorder
from voice_typing.config.settings import SettingsManager
from voice_typing.speech.engine import TranscriptBuffer
from voice_typing.speech.gemini_live import GeminiLiveClient, MODEL
from voice_typing.ui.settings_window import SettingsWindow
from voice_typing.ui.status_bar import StatusBar
from voice_typing.ui.tray import TrayIcon
from voice_typing.windows.hotkey import HotkeyManager, hotkey_name
from voice_typing.windows.startup import set_startup
from voice_typing.windows.text_injector import TextInjector, auto_space

DEFAULT_HOTKEY = 0x78  # VK_F9
ERROR_ALREADY_EXISTS = 183
MAX_HISTORY = 20
SILENCE_THRESHOLD = 0.005
_mutex_handle = None


def _acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, "VoiceType_SingleInstance")
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def _release_single_instance() -> None:
    global _mutex_handle
    if _mutex_handle is not None:
        try:
            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None


class WorkerSignals(QObject):
    partial_received = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    error = Signal(str)
    status = Signal(str)
    audio_level = Signal(float)
    history_changed = Signal(list)


class WorkerThread(QThread):
    def __init__(self, settings: SettingsManager) -> None:
        super().__init__()
        self._settings = settings
        self._signals = WorkerSignals()
        self._recorder = AudioRecorder()
        self._buffer = TranscriptBuffer()
        self._injector = TextInjector()
        self._hotkey_mgr = HotkeyManager()
        self._current_hotkey_vk: int | None = None
        self._current_language: str = "auto"
        self._client: GeminiLiveClient | None = None
        self._processor: TextProcessor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._should_stop = False
        self._last_injected = ""
        self._last_injected_raw = ""
        self._last_inject_time = 0.0
        self._last_level = 0.0
        self._silence_threshold: float = self._settings.get("silence_threshold", 0.005)
        self._history_path = Path(self._settings._path).parent / "history.json"
        self._history = self._load_history()

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        if self._recording:
            self._update_audio_level(audio_bytes)
        client = self._client
        loop = self._loop
        if client is not None and client.is_connected and loop is not None:
            future = asyncio.run_coroutine_threadsafe(
                client.send_audio(audio_bytes), loop
            )
            future.add_done_callback(self._on_audio_sent)

    def _update_audio_level(self, audio_bytes: bytes) -> None:
        # Keep this fast: it runs on the audio callback thread for every chunk.
        if len(audio_bytes) < 2 or len(audio_bytes) % 2 != 0:
            return
        samples = array("h")
        samples.frombytes(audio_bytes)
        if not samples:
            return
        sum_sq = 0
        for sample in samples:
            sum_sq += sample * sample
        normalized = math.sqrt(sum_sq / len(samples)) / 32768.0
        if normalized < self._silence_threshold:
            self._last_level *= 0.9
            self._signals.audio_level.emit(0.0)
            return
        # Gentle curve plus attack/release smoothing so the meter feels lively.
        level = max(normalized ** 0.5, self._last_level * 0.75)
        self._last_level = level
        self._signals.audio_level.emit(max(0.0, min(1.0, level)))

    def _on_audio_sent(self, future) -> None:
        try:
            future.result()
        except Exception:
            pass

    def _on_hotkey(self, vk_code: int) -> None:
        mode = self._settings.get("mode", "push_to_talk")
        if mode == "push_to_talk":
            self._start_recording()
        elif self._recording:
            self._finalize_and_inject()
        else:
            self._start_recording()

    def _on_hotkey_release(self, vk_code: int) -> None:
        self._finalize_and_inject()

    def reconfigure_hotkey(self) -> None:
        new_vk = self._settings.get("hotkey", DEFAULT_HOTKEY)
        if self._current_hotkey_vk is not None and self._current_hotkey_vk != new_vk:
            self._hotkey_mgr.unregister(self._current_hotkey_vk)
        mode = self._settings.get("mode", "push_to_talk")
        release_cb = self._on_hotkey_release if mode == "push_to_talk" else None
        self._hotkey_mgr.register(
            new_vk,
            self._on_hotkey,
            on_release=release_cb,
        )
        self._current_hotkey_vk = new_vk

    def update_settings(self) -> None:
        self.reconfigure_hotkey()
        self._silence_threshold = self._settings.get("silence_threshold", 0.005)
        api_key = self._settings.get("api_key", "")
        if not self._settings.get("fast_mode", True) and api_key:
            self._processor = TextProcessor(api_key=api_key)
        else:
            self._processor = None

        new_model = self._settings.get("model") or MODEL
        new_lang = self._settings.get("language", "auto")
        if self._client is not None:
            client_model = getattr(self._client, "_model", "")
            client_key = getattr(self._client, "_api_key", "")
            client_lang = getattr(self, "_current_language", "auto")
            if (
                client_key != api_key
                or client_model != new_model
                or client_lang != new_lang
            ):
                if self._loop is not None and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._client.disconnect(), self._loop
                    )
                elif self._loop is not None:
                    try:
                        self._loop.run_until_complete(self._client.disconnect())
                    except Exception:
                        pass

    def _start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            client = self._client
            if client is None or not client.is_connected:
                self._signals.error.emit(
                    "Not connected to Gemini Live yet - wait a moment and press the hotkey again"
                )
                return
            try:
                self._recorder.start(
                    callback=self._on_audio_chunk,
                    device_id=self._settings.get("microphone_device_id"),
                )
            except Exception:
                self._signals.error.emit("Failed to start microphone")
                return
            self._recording = True
        self._signals.recording_started.emit()

    def _inject(self, text: str) -> None:
        if not text:
            return
        raw = text
        text = auto_space(self._last_injected, text)
        self._last_injected = text
        if self._injector.inject(text):
            self._append_history(raw)

    def _re_inject(self, text: str) -> None:
        # Re-insert previously dictated text without touching history.
        if not text:
            return
        text = auto_space(self._last_injected, text)
        self._last_injected = text
        self._injector.inject(text)

    def _load_history(self) -> list[str]:
        try:
            if not self._history_path.exists():
                return []
            loaded = json.loads(self._history_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                return []
            return [str(item) for item in loaded][-MAX_HISTORY:]
        except (OSError, ValueError, UnicodeDecodeError):
            return []

    def _append_history(self, text: str) -> None:
        if self._history and self._history[-1] == text:
            return
        self._history.append(text)
        if len(self._history) > MAX_HISTORY:
            del self._history[:-MAX_HISTORY]
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(
                json.dumps(self._history, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        self._signals.history_changed.emit(list(self._history))

    def _inject_processed(self, future: asyncio.Future, raw: str) -> None:
        try:
            text = future.result()
        except Exception:
            text = raw
        self._inject(text)

    def _finalize_and_inject(self, keep_recording: bool = False) -> None:
        with self._lock:
            if not self._recording:
                return
            if not keep_recording:
                self._recorder.stop()
                self._recording = False
        if not keep_recording:
            self._signals.recording_stopped.emit()
        text = self._buffer.finalize()
        if not text.strip():
            return
        now = time.monotonic()
        if (
            self._last_injected_raw == text.strip()
            and now - self._last_inject_time < 0.5
        ):
            return
        self._last_injected_raw = text.strip()
        self._last_inject_time = now
        if self._processor is None or self._loop is None:
            self._inject(text)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            future = asyncio.ensure_future(self._processor.process(text))
            future.add_done_callback(
                lambda f: self._inject_processed(f, text)
            )
        else:
            future = asyncio.run_coroutine_threadsafe(
                self._processor.process(text), self._loop
            )
            try:
                text = future.result(timeout=4)
            except Exception:
                pass
            self._inject(text)

    def _on_partial(self, text: str) -> None:
        self._buffer.add_partial(text)
        self._signals.partial_received.emit(text)

    def _on_final(self, text: str) -> None:
        if text:
            self._buffer.add_partial(text)
        self._finalize_and_inject(
            keep_recording=(
                self._settings.get("mode", "push_to_talk") == "push_to_talk"
            )
        )

    def _sleep(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while not self._should_stop and time.monotonic() < deadline:
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        return self._should_stop

    def stop(self) -> None:
        self._should_stop = True
        with self._lock:
            if self._recording:
                try:
                    self._recorder.stop()
                except Exception:
                    pass
                self._recording = False
        client = self._client
        if client is not None:
            try:
                client.abort()
            except Exception:
                pass
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        try:
            self._hotkey_mgr.stop()
        except Exception:
            pass

    def _cleanup(self) -> None:
        client = self._client
        loop = self._loop
        if loop is not None and client is not None and client.is_connected:
            try:
                loop.run_until_complete(client.disconnect())
            except Exception:
                pass
        elif client is not None:
            try:
                client.abort()
            except Exception:
                pass
        self._hotkey_mgr.stop()
        if loop is not None:
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None

    def run(self) -> None:
        api_key = self._settings.get("api_key", "")
        if not api_key:
            self._signals.error.emit("No API key configured")
            return
        self.reconfigure_hotkey()
        self._hotkey_mgr.start()
        self._hotkey_mgr.wait_ready(timeout=2.0)
        failures = self._hotkey_mgr.registration_failures()
        if failures:
            self._signals.error.emit(
                "Hotkey "
                + ", ".join(hotkey_name(v) for v in failures)
                + " failed to register - another app may already be using it"
            )
        last_error = ""
        try:
            self._signals.status.emit("Connecting to Gemini Live...")
            while not self._should_stop:
                self._client = GeminiLiveClient(
                    api_key=api_key,
                    model=self._settings.get("model") or MODEL,
                )
                self._current_language = self._settings.get("language", "auto")
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(
                        self._client.connect(
                            language=self._current_language
                        )
                    )
                    break
                except Exception as exc:
                    last_error = str(exc)
                    if self._loop is not None:
                        self._loop.close()
                        self._loop = None
                    self._client = None
                    if self._should_stop:
                        return
                    if self._sleep(3):
                        return
            if self._client is None or not self._client.is_connected:
                self._signals.error.emit(
                    "Cannot connect to Gemini Live: "
                    f"{last_error[:300] or 'unknown error'} - check your API key and internet"
                )
                return
            if not self._settings.get("fast_mode", True):
                self._processor = TextProcessor(api_key=api_key)
            while not self._should_stop:
                loop = self._loop
                if loop is None:
                    return
                try:
                    loop.run_until_complete(
                        self._client.receive_transcript(
                            on_partial=self._on_partial, on_final=self._on_final
                        )
                    )
                except Exception as exc:
                    last_error = str(exc)
                    if self._should_stop:
                        break
                    self._signals.status.emit("Connection lost - reconnecting...")
                if self._should_stop:
                    break
                if self._client.is_connected:
                    continue
                self._stop_recording_on_connection_lost()
                if loop is not None:
                    loop.close()
                    self._loop = None
                if not self._reconnect():
                    self._signals.error.emit(
                        "Connection lost and could not reconnect: "
                        f"{last_error[:300] or 'unknown error'}"
                    )
                    return
        except Exception as exc:
            self._signals.error.emit(
                f"Speech engine connection lost: {str(exc)[:300]}"
            )
        finally:
            self._cleanup()

    def _stop_recording_on_connection_lost(self) -> None:
        stopped = False
        with self._lock:
            if self._recording:
                self._recorder.stop()
                self._recording = False
                stopped = True
        if stopped:
            self._signals.recording_stopped.emit()
            text = self._buffer.finalize()
            if text.strip():
                self._inject(text)

    def _reconnect(self) -> bool:
        api_key = self._settings.get("api_key", "")
        delays = (2, 4, 8)
        last_error = ""
        for attempt, delay in enumerate(delays, start=1):
            if self._should_stop:
                return False
            if self._sleep(delay):
                return False
            loop = None
            try:
                client = GeminiLiveClient(
                    api_key=api_key,
                    model=self._settings.get("model") or MODEL,
                )
                self._current_language = self._settings.get("language", "auto")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    client.connect(language=self._current_language)
                )
            except Exception as exc:
                last_error = str(exc)
                if loop is not None:
                    loop.close()
                self._signals.status.emit(
                    f"Reconnect attempt {attempt} of {len(delays)} failed - retrying..."
                )
                continue
            self._client = client
            self._loop = loop
            self._signals.status.emit("Reconnected to Gemini Live")
            return True
        return False


class _MicTester(QThread):
    finished_test = Signal(bool, str)

    def __init__(self, device_id: int | None = None) -> None:
        super().__init__()
        self._device_id = device_id

    def run(self) -> None:
        try:
            rec = AudioRecorder()
            rec.start(
                callback=lambda b: None,
                device_id=self._device_id,
            )
            time.sleep(0.3)
            rec.stop()
            self.finished_test.emit(True, "Microphone is working.")
        except Exception as e:
            self.finished_test.emit(False, f"Microphone error: {e}")


class VoiceTypeApp:
    def __init__(self) -> None:
        self._qapp = QApplication.instance() or QApplication(sys.argv)
        self._qapp.setQuitOnLastWindowClosed(False)
        try:
            asset_icon = Path(__file__).resolve().parent / "assets" / "icon.png"
            if asset_icon.exists() and hasattr(self._qapp, "setWindowIcon"):
                self._qapp.setWindowIcon(QIcon(str(asset_icon)))
        except Exception:
            pass
        config_dir = Path.home() / "AppData" / "Roaming" / "VoiceType"
        self._settings = SettingsManager(config_dir / "settings.json")
        self._settings.load()
        self._tray = TrayIcon()
        self._status_bar = StatusBar(
            on_position_changed=self._on_status_bar_moved,
            saved_position=(
                (self._settings.get("status_bar_x"), self._settings.get("status_bar_y"))
                if self._settings.get("status_bar_x") is not None
                else None
            ),
            style=self._settings.get("capsule_style", "pill"),
        )
        self._status_bar.set_opacity(self._settings.get("opacity", 0.94))
        self._settings_win: SettingsWindow | None = None
        self._worker: WorkerThread | None = None
        self._mic_tester: _MicTester | None = None

    def run(self) -> int:
        self._tray.signals.start_recording.connect(self._start_recording)
        self._tray.signals.stop_recording.connect(self._stop_recording)
        self._tray.signals.open_settings.connect(self._open_settings)
        self._tray.signals.exit_app.connect(self._exit)
        self._tray.signals.mode_changed.connect(self._on_mode_changed)
        self._tray.signals.language_changed.connect(self._on_language_changed)
        self._tray.signals.fast_mode_toggled.connect(self._on_fast_mode_toggled)
        self._tray.signals.clear_history.connect(self._on_clear_history)
        self._tray.signals.test_microphone.connect(self._on_test_microphone)
        self._tray.signals.re_inject.connect(self._on_re_inject)
        self._tray.signals.show_status_bar.connect(self._status_bar.show)
        self._status_bar.signals.start_recording.connect(self._start_recording)
        self._status_bar.signals.stop_recording.connect(self._stop_recording)
        self._status_bar.signals.open_settings.connect(self._open_settings)
        self._status_bar.signals.exit_app.connect(self._exit)
        self._run_setup_wizard()
        self._tray.set_language(self._settings.get("language", "auto"))
        self._tray.set_fast_mode(self._settings.get("fast_mode", True))
        self._tray.show()
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
        set_startup(self._settings.get("start_with_windows", False))
        self._status_bar.set_hotkey_name(
            hotkey_name(self._settings.get("hotkey", DEFAULT_HOTKEY))
        )
        self._spawn_worker()
        worker = self._worker
        if worker is not None:
            self._tray.set_history(list(worker._history))
        return self._qapp.exec()

    def _start_recording(self) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning():
            self._spawn_worker()
            worker = self._worker
        if worker is None:
            return
        worker._start_recording()

    def _on_status_bar_moved(self, x: int, y: int) -> None:
        self._settings.set("status_bar_x", x)
        self._settings.set("status_bar_y", y)
        self._settings.save()

    def _spawn_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        if self._worker is not None and not self._worker.isRunning():
            self._worker = None
        self._worker = WorkerThread(self._settings)
        self._worker._signals.recording_started.connect(self._on_recording_started)
        self._worker._signals.recording_stopped.connect(self._on_recording_stopped)
        self._worker._signals.partial_received.connect(self._on_partial)
        self._worker._signals.error.connect(self._on_error)
        self._worker._signals.status.connect(self._on_status)
        self._worker._signals.audio_level.connect(self._status_bar.set_level)
        self._worker._signals.history_changed.connect(self._tray.set_history)
        self._worker.start()

    def _on_re_inject(self, text: str) -> None:
        worker = self._worker
        if worker is not None:
            worker._re_inject(text)

    def _stop_recording(self) -> None:
        if self._worker is not None:
            self._worker._finalize_and_inject()

    def _on_recording_started(self) -> None:
        self._tray.update_recording_state(True)
        self._status_bar.update_recording_state(True)
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
        self._status_bar.set_state("listening", "Listening...")
        if self._settings.get("sound_feedback", True):
            winsound.MessageBeep(winsound.MB_OK)

    def _on_recording_stopped(self) -> None:
        self._tray.update_recording_state(False)
        self._status_bar.update_recording_state(False)
        self._status_bar.set_state("ready")
        if self._settings.get("sound_feedback", True):
            winsound.MessageBeep(winsound.MB_ICONASTERISK)

    def _on_partial(self, text: str) -> None:
        self._status_bar.set_state("listening", text)

    def _on_error(self, msg: str) -> None:
        self._status_bar.show()
        self._status_bar.set_state("error", msg)
        self._tray.set_status("Error")

    def _on_status(self, msg: str) -> None:
        self._status_bar.set_state("ready", msg)
        self._tray.set_status("Connecting...")

    def _on_test_microphone(self) -> None:
        if self._mic_tester is not None and self._mic_tester.isRunning():
            return
        self._mic_tester = _MicTester(
            device_id=self._settings.get("microphone_device_id")
        )
        self._mic_tester.finished_test.connect(self._on_mic_test_result)
        self._mic_tester.start()

    def _on_mic_test_result(self, success: bool, msg: str) -> None:
        if success:
            QMessageBox.information(
                None, "Microphone Test", msg
            )
        else:
            QMessageBox.warning(
                None, "Microphone Test", msg
            )

    def _on_mode_changed(self, mode: str) -> None:
        self._settings.set("mode", mode)
        self._settings.save()
        if self._worker is not None:
            self._worker.reconfigure_hotkey()

    def _on_language_changed(self, lang: str) -> None:
        self._settings.set("language", lang)
        self._settings.save()
        if self._worker is not None and self._worker.isRunning():
            self._worker.update_settings()

    def _on_fast_mode_toggled(self, fast: bool) -> None:
        self._settings.set("fast_mode", fast)
        self._settings.save()
        if self._worker is not None and self._worker.isRunning():
            self._worker.update_settings()

    def _on_clear_history(self) -> None:
        if self._worker is not None:
            self._worker._history.clear()
            self._worker._save_history()
        self._tray.set_history([])

    def _open_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self._settings)
            self._settings_win.saved.connect(self._on_settings_saved)
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _on_settings_saved(self) -> None:
        self._status_bar.set_hotkey_name(
            hotkey_name(self._settings.get("hotkey", DEFAULT_HOTKEY))
        )
        self._status_bar.set_style(self._settings.get("capsule_style", "pill"))
        self._status_bar.set_opacity(self._settings.get("opacity", 0.94))
        self._tray.set_mode(self._settings.get("mode", "push_to_talk"))
        self._tray.set_language(self._settings.get("language", "auto"))
        self._tray.set_fast_mode(self._settings.get("fast_mode", True))
        if self._worker is not None and self._worker.isRunning():
            self._worker.reconfigure_hotkey()
            self._worker.update_settings()
        else:
            self._spawn_worker()
        set_startup(self._settings.get("start_with_windows", False))
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
        else:
            self._status_bar.close()


    def _run_setup_wizard(self) -> None:
        if self._settings.get("api_key"):
            return
        api_key, ok = QInputDialog.getText(
            None, "VoiceType Setup", "Enter your Gemini API Key:"
        )
        if ok and api_key.strip():
            self._settings.set("api_key", api_key.strip())
            self._settings.save()
        else:
            QMessageBox.warning(
                None,
                "VoiceType Setup",
                "No API key entered. You can configure it later in Settings.",
            )

    def _exit(self, force_exit: bool = True) -> None:
        try:
            if self._worker is not None and self._worker.isRunning():
                self._worker.stop()
                if not self._worker.wait(500):
                    self._worker.terminate()
            if self._mic_tester is not None and self._mic_tester.isRunning():
                self._mic_tester.terminate()
            if self._settings_win is not None:
                self._settings_win.close()
            self._status_bar.close()
            self._tray.hide()
        except Exception:
            pass
        finally:
            _release_single_instance()
            self._qapp.quit()
            if force_exit:
                import os
                os._exit(0)


def main() -> int:
    if not _acquire_single_instance():
        app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "VoiceType",
            "VoiceType is already running. Check the system tray (bottom-right).",
        )
        return 1
    exit_code = 0
    try:
        app = VoiceTypeApp()
        exit_code = app.run()
    finally:
        _release_single_instance()
    import os
    os._exit(exit_code or 0)


if __name__ == "__main__":
    sys.exit(main())
