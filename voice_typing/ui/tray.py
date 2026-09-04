# voice_typing/ui/tray.py
from __future__ import annotations

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

from voice_typing.config.settings import get_asset_path


class TraySignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    mode_changed = Signal(str)
    language_changed = Signal(str)
    fast_mode_toggled = Signal(bool)
    clear_history = Signal()
    re_inject = Signal(str)
    show_status_bar = Signal()
    open_history = Signal()
    check_update = Signal()


class TrayIcon:
    def __init__(self) -> None:
        self.signals = TraySignals()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._mode: str = "push_to_talk"
        self._language: str = "auto"
        self._fast_mode: bool = True
        self._recording: bool = False
        self._status_text: str = "Ready"
        self._history: list[str] = []

    def _make_icon(self) -> QIcon:
        try:
            asset_path = get_asset_path("icon.png")
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

        lang_menu = self._menu.addMenu("Language (ภาษา)")
        for code, label in [("auto", "Auto (Thai + English)"), ("thai", "Thai (ไทย)"), ("english", "English")]:
            act = QAction(label, lang_menu)
            act.setCheckable(True)
            act.setChecked(self._language == code)
            act.triggered.connect(lambda checked=False, c=code: self._set_language(c))
            lang_menu.addAction(act)

        fast_action = QAction("Fast Mode (Direct Input)", self._menu)
        fast_action.setCheckable(True)
        fast_action.setChecked(self._fast_mode)
        fast_action.triggered.connect(self._toggle_fast_mode)
        self._menu.addAction(fast_action)

        history_act = QAction("Browse History...", self._menu)
        history_act.triggered.connect(self.signals.open_history.emit)
        self._menu.addAction(history_act)

        self._menu.addSeparator()
        settings_action = QAction("Settings", self._menu)
        settings_action.triggered.connect(self.signals.open_settings.emit)
        self._menu.addAction(settings_action)

        test_action = QAction("Test Microphone", self._menu)
        test_action.triggered.connect(self.signals.test_microphone.emit)
        self._menu.addAction(test_action)

        self._menu.addSeparator()
        update_action = QAction("Check for Updates...", self._menu)
        update_action.triggered.connect(self.signals.check_update.emit)
        self._menu.addAction(update_action)
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

    def _set_language(self, lang: str) -> None:
        self._language = lang
        self._build_menu()
        self.signals.language_changed.emit(lang)

    def set_language(self, lang: str) -> None:
        self._language = lang
        self._build_menu()

    def _toggle_fast_mode(self, checked: bool) -> None:
        self._fast_mode = checked
        self._build_menu()
        self.signals.fast_mode_toggled.emit(checked)

    def set_fast_mode(self, fast: bool) -> None:
        self._fast_mode = fast
        self._build_menu()

    def set_history(self, items: list) -> None:
        self._history = items
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
        elif reason == QSystemTrayIcon.ActivationReason.Context and self._menu is not None:
            self._build_menu()
            self._menu.popup(QCursor.pos())

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()
