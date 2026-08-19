# voice_typing/app.py
from __future__ import annotations

import asyncio
import ctypes
import sys
import threading
import time
import winsound
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject
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
_mutex_handle = None


def _acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    _mutex_handle = kernel32.CreateMutexW(None, False, "VoiceType_SingleInstance")
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


class WorkerSignals(QObject):
    partial_received = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    error = Signal(str)
    status = Signal(str)


class WorkerThread(QThread):
    def __init__(self, settings: SettingsManager) -> None:
        super().__init__()
        self._settings = settings
        self._signals = WorkerSignals()
        self._recorder = AudioRecorder()
        self._buffer = TranscriptBuffer()
        self._injector = TextInjector()
        self._hotkey_mgr = HotkeyManager()
        self._client: GeminiLiveClient | None = None
        self._processor: TextProcessor | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._recording = False
        self._should_stop = False
        self._last_injected = ""
        self._last_injected_raw = ""
        self._last_inject_time = 0.0

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        client = self._client
        loop = self._loop
        if client is not None and client.is_connected and loop is not None:
            future = asyncio.run_coroutine_threadsafe(
                client.send_audio(audio_bytes), loop
            )
            future.add_done_callback(self._on_audio_sent)

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
        mode = self._settings.get("mode", "push_to_talk")
        release_cb = self._on_hotkey_release if mode == "push_to_talk" else None
        self._hotkey_mgr.register(
            self._settings.get("hotkey", DEFAULT_HOTKEY),
            self._on_hotkey,
            on_release=release_cb,
        )

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
        text = auto_space(self._last_injected, text)
        self._last_injected = text
        self._injector.inject(text)

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
            and now - self._last_inject_time < 3.0
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

    def _cleanup(self) -> None:
        loop = self._loop
        if loop is not None and self._client is not None and self._client.is_connected:
            try:
                loop.run_until_complete(self._client.disconnect())
            except Exception:
                pass
        self._hotkey_mgr.stop()
        if loop is not None:
            loop.close()
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
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                try:
                    self._loop.run_until_complete(
                        self._client.connect(
                            language=self._settings.get("language", "auto")
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
                    time.sleep(3)
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
            time.sleep(delay)
            if self._should_stop:
                return False
            loop = None
            try:
                client = GeminiLiveClient(
                    api_key=api_key,
                    model=self._settings.get("model") or MODEL,
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    client.connect(language=self._settings.get("language", "auto"))
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


class VoiceTypeApp:
    def __init__(self) -> None:
        self._qapp = QApplication(sys.argv)
        self._qapp.setQuitOnLastWindowClosed(False)
        config_dir = Path.home() / "AppData" / "Roaming" / "VoiceType"
        self._settings = SettingsManager(config_dir / "settings.json")
        self._settings.load()
        self._tray = TrayIcon()
        self._status_bar = StatusBar()
        self._settings_win: SettingsWindow | None = None
        self._worker: WorkerThread | None = None

    def run(self) -> int:
        self._tray.signals.start_recording.connect(self._start_recording)
        self._tray.signals.stop_recording.connect(self._stop_recording)
        self._tray.signals.open_settings.connect(self._open_settings)
        self._tray.signals.exit_app.connect(self._exit)
        self._tray.signals.mode_changed.connect(self._on_mode_changed)
        self._tray.signals.test_microphone.connect(self._on_test_microphone)
        self._status_bar.signals.start_recording.connect(self._start_recording)
        self._status_bar.signals.stop_recording.connect(self._stop_recording)
        self._status_bar.signals.open_settings.connect(self._open_settings)
        self._status_bar.signals.exit_app.connect(self._exit)
        self._run_setup_wizard()
        self._tray.show()
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
        set_startup(self._settings.get("start_with_windows", False))
        self._status_bar.set_hotkey_name(
            hotkey_name(self._settings.get("hotkey", DEFAULT_HOTKEY))
        )
        self._spawn_worker()
        return self._qapp.exec()

    def _start_recording(self) -> None:
        worker = self._worker
        if worker is None or not worker.isRunning():
            self._spawn_worker()
            worker = self._worker
        if worker is None:
            return
        worker._start_recording()

    def _spawn_worker(self) -> None:
        if self._worker is not None:
            return
        self._worker = WorkerThread(self._settings)
        self._worker._signals.recording_started.connect(self._on_recording_started)
        self._worker._signals.recording_stopped.connect(self._on_recording_stopped)
        self._worker._signals.partial_received.connect(self._on_partial)
        self._worker._signals.error.connect(self._on_error)
        self._worker._signals.status.connect(self._on_status)
        self._worker.start()

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
        try:
            rec = AudioRecorder()
            rec.start(
                callback=lambda b: None,
                device_id=self._settings.get("microphone_device_id"),
            )
            QThread.msleep(300)
            rec.stop()
            QMessageBox.information(
                None, "Microphone Test", "Microphone is working."
            )
        except Exception as e:
            QMessageBox.warning(
                None, "Microphone Test", f"Microphone error: {e}"
            )

    def _on_mode_changed(self, mode: str) -> None:
        self._settings.set("mode", mode)
        self._settings.save()
        if self._worker is not None:
            self._worker.reconfigure_hotkey()

    def _open_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self._settings)
            self._settings_win.saved.connect(self._on_settings_saved)
        self._settings_win.show()

    def _on_settings_saved(self) -> None:
        self._status_bar.set_hotkey_name(
            hotkey_name(self._settings.get("hotkey", DEFAULT_HOTKEY))
        )
        self._tray.set_mode(self._settings.get("mode", "push_to_talk"))
        if self._worker is not None:
            self._worker.reconfigure_hotkey()
        set_startup(self._settings.get("start_with_windows", False))

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

    def _exit(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker._finalize_and_inject()
            self._worker._should_stop = True
            self._worker.wait(15000)
        self._status_bar.close()
        self._tray.hide()
        self._qapp.quit()


def main() -> int:
    if not _acquire_single_instance():
        app = QApplication(sys.argv)
        QMessageBox.warning(
            None,
            "VoiceType",
            "VoiceType is already running. Check the system tray (bottom-right).",
        )
        return 1
    app = VoiceTypeApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
