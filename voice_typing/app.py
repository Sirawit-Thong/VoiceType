# voice_typing/app.py
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import QApplication

from voice_typing.ai.text_processor import TextProcessor
from voice_typing.audio.recorder import AudioRecorder
from voice_typing.config.settings import SettingsManager
from voice_typing.speech.engine import TranscriptBuffer
from voice_typing.speech.gemini_live import GeminiLiveClient
from voice_typing.ui.settings_window import SettingsWindow
from voice_typing.ui.status_bar import StatusBar
from voice_typing.ui.tray import TrayIcon
from voice_typing.windows.hotkey import HotkeyManager
from voice_typing.windows.text_injector import TextInjector


class WorkerSignals(QObject):
    partial_received = Signal(str)
    final_received = Signal(str)
    recording_started = Signal()
    recording_stopped = Signal()
    error = Signal(str)


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
        self._is_toggle_mode = False
        self._recording = False

    def _on_audio_chunk(self, audio_bytes: bytes) -> None:
        if self._client is not None and self._client.is_connected:
            asyncio.run_coroutine_threadsafe(
                self._client.send_audio(audio_bytes), self._loop
            )

    def _on_hotkey(self, vk_code: int) -> None:
        if self._is_toggle_mode:
            if self._recording:
                self._finalize_and_inject()
            else:
                self._start_recording()
        else:
            if self._recording:
                self._finalize_and_inject()

    def _start_recording(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._signals.recording_started.emit()
        self._recorder.start(callback=self._on_audio_chunk)

    def _finalize_and_inject(self) -> None:
        self._recorder.stop()
        self._recording = False
        self._signals.recording_stopped.emit()
        text = self._buffer.finalize()
        if text.strip():
            self._injector.inject(text)

    def _on_partial(self, text: str) -> None:
        self._buffer.add_partial(text)
        self._signals.partial_received.emit(text)

    def _on_final(self, text: str) -> None:
        self._buffer.add_partial(text)
        self._finalize_and_inject()

    def run(self) -> None:
        api_key = self._settings.get("api_key", "")
        if not api_key:
            self._signals.error.emit("No API key configured")
            return

        self._client = GeminiLiveClient(api_key=api_key)

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        loop = self._loop
        loop.run_until_complete(self._client.connect())

        self._hotkey_mgr.register(
            self._settings.get("hotkey", 0x7E), self._on_hotkey
        )
        self._hotkey_mgr.start()

        while self._client.is_connected:
            loop.run_until_complete(
                self._client.receive_transcript(
                    on_partial=self._on_partial, on_final=self._on_final
                )
            )

        loop.run_until_complete(self._client.disconnect())
        self._hotkey_mgr.stop()


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
        self._tray.show()
        return self._qapp.exec()

    def _start_recording(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = WorkerThread(self._settings)
        self._worker._signals.recording_started.connect(self._on_recording_started)
        self._worker._signals.recording_stopped.connect(self._on_recording_stopped)
        self._worker._signals.partial_received.connect(self._on_partial)
        self._worker._signals.error.connect(self._on_error)
        self._worker.start()

    def _stop_recording(self) -> None:
        if self._worker is not None:
            self._worker._finalize_and_inject()

    def _on_recording_started(self) -> None:
        self._tray.update_recording_state(True)
        if self._settings.get("show_status_bar", True):
            self._status_bar.show()
            self._status_bar.set_state("listening", "Listening...")

    def _on_recording_stopped(self) -> None:
        self._tray.update_recording_state(False)
        self._status_bar.set_state("ready")
        self._status_bar.hide()

    def _on_partial(self, text: str) -> None:
        self._status_bar.set_state("listening", text)

    def _on_error(self, msg: str) -> None:
        self._status_bar.set_state("error", msg)

    def _on_mode_changed(self, mode: str) -> None:
        self._settings.set("mode", mode)
        self._settings.save()

    def _open_settings(self) -> None:
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self._settings)
        self._settings_win.show()

    def _exit(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker._finalize_and_inject()
            self._worker.quit()
            self._worker.wait(2000)
        self._status_bar.close()
        self._tray.hide()
        self._qapp.quit()


def main() -> int:
    app = VoiceTypeApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
