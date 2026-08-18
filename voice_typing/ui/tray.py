# voice_typing/ui/tray.py
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TraySignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    mode_changed = Signal(str)


class TrayIcon:
    def __init__(self) -> None:
        self.signals = TraySignals()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._mode: str = "push_to_talk"
        self._recording: bool = False

    def _make_icon(self) -> QIcon:
        icon = QIcon.fromTheme("audio-input-microphone")
        if not icon.isNull():
            return icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setBrush(QColor("#1a73e8"))
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()
        return QIcon(pixmap)

    def show(self) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(self._make_icon())
        self._tray.setToolTip("VoiceType - Ready")
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self) -> None:
        if self._menu is None:
            return
        self._menu.clear()
        if self._recording:
            action = QAction("Stop Recording")
            action.triggered.connect(self.signals.stop_recording.emit)
        else:
            action = QAction("Start Recording")
            action.triggered.connect(self.signals.start_recording.emit)
        self._menu.addAction(action)

        mode_menu = self._menu.addMenu("Mode")
        ptt_action = QAction("Push-to-Talk (hold to record)")
        ptt_action.setCheckable(True)
        ptt_action.setChecked(self._mode == "push_to_talk")
        ptt_action.triggered.connect(lambda: self._set_mode("push_to_talk"))
        mode_menu.addAction(ptt_action)

        toggle_action = QAction("Toggle (press to start/stop)")
        toggle_action.setCheckable(True)
        toggle_action.setChecked(self._mode == "toggle")
        toggle_action.triggered.connect(lambda: self._set_mode("toggle"))
        mode_menu.addAction(toggle_action)

        self._menu.addSeparator()
        settings_action = QAction("Settings")
        settings_action.triggered.connect(self.signals.open_settings.emit)
        self._menu.addAction(settings_action)

        test_action = QAction("Test Microphone")
        test_action.triggered.connect(self.signals.test_microphone.emit)
        self._menu.addAction(test_action)

        self._menu.addSeparator()
        exit_action = QAction("Exit")
        exit_action.triggered.connect(self.signals.exit_app.emit)
        self._menu.addAction(exit_action)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._build_menu()
        self.signals.mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._build_menu()

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        self._build_menu()
        if self._tray is not None:
            if recording:
                self._tray.setToolTip("VoiceType - Recording...")
            else:
                self._tray.setToolTip("VoiceType - Ready")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.signals.start_recording.emit()

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()