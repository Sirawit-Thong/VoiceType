# voice_typing/ui/tray.py
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TraySignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    mode_changed = Signal(str)
    re_inject = Signal(str)
    show_status_bar = Signal()


class TrayIcon:
    def __init__(self) -> None:
        self.signals = TraySignals()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._mode: str = "push_to_talk"
        self._recording: bool = False
        self._status_text: str = "Ready"
        self._history: list[str] = []

    def _make_icon(self) -> QIcon:
        try:
            asset_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
            if asset_path.exists():
                icon = QIcon(str(asset_path))
                if not icon.isNull():
                    return icon
        except Exception:
            pass
        try:
            icon = QIcon.fromTheme("audio-input-microphone")
            if not icon.isNull():
                return icon
        except Exception:
            pass
        try:
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor("transparent"))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1a73e8"))
            painter.drawEllipse(2, 2, 28, 28)
            painter.setPen(QPen(QColor("white"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(12, 13, 8, 8, 0, -180 * 16)
            painter.drawLine(16, 21, 16, 24)
            painter.drawLine(12, 24, 20, 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("white"))
            painter.drawRoundedRect(13, 6, 6, 10, 2, 2)
            painter.end()
            return QIcon(pixmap)
        except Exception:
            return QIcon()


    def show(self) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(self._make_icon())
        self._tray.setToolTip("VoiceType - Ready")
        self._menu = QMenu()
        self._menu.setStyleSheet(
            "QMenu { background-color: #202124; color: #e8eaed; "
            "border: 1px solid #3c4043; border-radius: 8px; padding: 6px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 6px; }"
            "QMenu::item:selected { background-color: #303134; }"
            "QMenu::separator { height: 1px; background-color: #3c4043; "
            "margin: 4px 8px; }"
        )
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self) -> None:
        if self._menu is None:
            return
        self._menu.clear()
        status_action = QAction(f"Status: {self._status_text}", self._menu)
        status_action.setEnabled(False)
        self._menu.addAction(status_action)
        self._menu.addSeparator()
        if self._recording:
            action = QAction("Stop Recording", self._menu)
            action.triggered.connect(self.signals.stop_recording.emit)
        else:
            action = QAction("Start Recording", self._menu)
            action.triggered.connect(self.signals.start_recording.emit)
        self._menu.addAction(action)

        mode_menu = self._menu.addMenu("Mode")
        ptt_action = QAction("Push-to-Talk (hold to record)", mode_menu)
        ptt_action.setCheckable(True)
        ptt_action.setChecked(self._mode == "push_to_talk")
        ptt_action.triggered.connect(lambda: self._set_mode("push_to_talk"))
        mode_menu.addAction(ptt_action)

        toggle_action = QAction("Toggle (press to start/stop)", mode_menu)
        toggle_action.setCheckable(True)
        toggle_action.setChecked(self._mode == "toggle")
        toggle_action.triggered.connect(lambda: self._set_mode("toggle"))
        mode_menu.addAction(toggle_action)

        history_menu = self._menu.addMenu("ล่าสุด")
        if self._history:
            # Newest first, at most 10 entries, labels truncated with "…"
            for full_text in reversed(self._history[-10:]):
                if len(full_text) > 35:
                    label = full_text[:35].rstrip() + "…"
                else:
                    label = full_text
                item = QAction(label, history_menu)
                item.setToolTip(full_text)
                item.triggered.connect(
                    lambda checked=False, text=full_text: self.signals.re_inject.emit(text)
                )
                history_menu.addAction(item)
        else:
            empty_action = QAction("— ว่างเปล่า —", history_menu)
            empty_action.setEnabled(False)
            history_menu.addAction(empty_action)

        self._menu.addSeparator()
        settings_action = QAction("Settings", self._menu)
        settings_action.triggered.connect(self.signals.open_settings.emit)
        self._menu.addAction(settings_action)

        test_action = QAction("Test Microphone", self._menu)
        test_action.triggered.connect(self.signals.test_microphone.emit)
        self._menu.addAction(test_action)

        self._menu.addSeparator()
        exit_action = QAction("Exit", self._menu)
        exit_action.triggered.connect(self.signals.exit_app.emit)
        self._menu.addAction(exit_action)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._build_menu()
        self.signals.mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._build_menu()

    def set_history(self, items: list[str]) -> None:
        self._history = list(items)
        if self._menu is not None:
            self._build_menu()

    def set_status(self, status: str) -> None:
        self._status_text = status
        self._build_menu()
        if self._tray is not None:
            self._tray.setToolTip(f"VoiceType - {status}")

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        self.set_status("Recording..." if recording else "Ready")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.signals.show_status_bar.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            if self._menu is not None:
                self._build_menu()
                self._menu.popup(QCursor.pos())

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()