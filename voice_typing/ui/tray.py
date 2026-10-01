# voice_typing/ui/tray.py
"""UX Phase D: slim tray menu.

Order: status (dot) / Start-Stop / Mode / Language /
Open History in Settings / Settings / Test Microphone / Exit.

- Fast Mode UI was removed (Phase B). The worker `fast_mode` setting logic
  is unchanged (settings window + WorkerThread.update_settings); only the
  tray checkbox is gone. `TraySignals.fast_mode_toggled` is retained as a
  deprecated no-op signal for backward compatibility and is never emitted.
- Recent submenu was removed (Phase D, pre-approved decision): history now
  lives in Settings (History page). A single "Open History in Settings"
  entry replaces it. `TraySignals.clear_history` / `re_inject` are
  retained as deprecated no-op signals (never emitted) and
  `TrayIcon.set_history()` is a no-op shim that only stores the list.
- Status dot: green Ready/Recording, amber reconnecting, gray error/dead
  (mirrors capsule colors; see ui._theme toast/tray mapping note).
  Dot logic is untouched by Phase D.
- set_status() updates the dot row only (no menu rebuild).
"""
from __future__ import annotations

import logging

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
from PySide6.QtWidgets import (
    QMenu,
    QSystemTrayIcon,
)
from voice_typing.config.settings import get_asset_path
from voice_typing.ui._theme import (
    COLOR_ERROR_DEAD,
    COLOR_READY,
    COLOR_RECONNECTING,
    COLOR_TRAY_FALLBACK_BLUE,
    MENU_STYLESHEET,
    RECONNECT_HINTS,
    TRANSIENT_ERROR_HINTS,
)

log = logging.getLogger(__name__)

# Substrings mapping to the gray error/dead dot.
_ERROR_HINTS = (
    "error",
    "dead",
    "failed",
    "could not",
    "cannot",
    "not connected",
)


class TraySignals(QObject):
    start_recording = Signal()
    stop_recording = Signal()
    open_settings = Signal()
    open_history = Signal()
    test_microphone = Signal()
    exit_app = Signal()
    mode_changed = Signal(str)
    language_changed = Signal(str)
    # Deprecated (UX Phase B): Fast Mode UI removed from the tray. The
    # worker `fast_mode` setting logic is unchanged. Retained so existing
    # connections don't break; never emitted.
    fast_mode_toggled = Signal(bool)
    # Deprecated (UX Phase D): Recent submenu removed; history lives in
    # Settings. Retained so existing connections don't break; never
    # emitted (the app routes history through the settings HistoryPanel).
    clear_history = Signal()
    re_inject = Signal(str)
    show_status_bar = Signal()


def status_dot_color(status: str) -> str:
    """Map a status string to its tray dot color.

    Green (COLOR_READY) = Ready/Recording (healthy); amber
    (COLOR_RECONNECTING) = reconnecting *or* transient mic/inject nudge
    (both are non-dead warm states); gray (COLOR_ERROR_DEAD) =
    error/dead. Mirrors the capsule state colors. Hint sets live in
    ui._theme (RECONNECT_HINTS / TRANSIENT_ERROR_HINTS) — single source.
    """
    low = (status or "").lower()
    if any(h in low for h in RECONNECT_HINTS):
        return COLOR_RECONNECTING
    if any(h in low for h in TRANSIENT_ERROR_HINTS):
        return COLOR_RECONNECTING
    if any(h in low for h in _ERROR_HINTS):
        return COLOR_ERROR_DEAD
    return COLOR_READY


class TrayIcon:
    def __init__(self) -> None:
        self.signals = TraySignals()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._mode: str = "push_to_talk"
        self._language: str = "auto"
        self._recording: bool = False
        self._status_text: str = "Ready"
        self._status_dot_color: str = COLOR_READY
        # Phase D shim: stored only, never rendered in the tray.
        self._history: list[str] = []
        # Held refs so set_status stays surgical (no rebuild).
        self._status_action: QAction | None = None
        self._start_stop_action: QAction | None = None
        self._mode_actions: dict[str, QAction] = {}
        self._lang_actions: dict[str, QAction] = {}

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
            painter.setBrush(QColor(COLOR_TRAY_FALLBACK_BLUE))
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

    @staticmethod
    def _make_dot_icon(color: str) -> QIcon:
        pixmap = QPixmap(12, 12)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(2, 2, 8, 8)
        finally:
            painter.end()
        return QIcon(pixmap)

    def show(self) -> None:
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(self._make_icon())
        self._tray.setToolTip("VoiceType - Ready")
        self._menu = QMenu()
        self._menu.setStyleSheet(MENU_STYLESHEET)
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self) -> None:
        """Full menu build (show/init only). Order: status / Start-Stop /
        Mode / Language / Open History in Settings / Settings /
        Test Microphone / Exit."""
        if self._menu is None:
            return
        self._menu.clear()
        self._mode_actions = {}
        self._lang_actions = {}

        self._status_action = QAction(self._menu)
        self._status_action.setEnabled(False)
        self._refresh_status_row()
        self._menu.addAction(self._status_action)
        self._menu.addSeparator()

        self._start_stop_action = QAction(self._menu)
        self._menu.addAction(self._start_stop_action)
        self._refresh_start_stop_row()

        mode_menu = self._menu.addMenu("Mode")
        for mode, label in (
            ("push_to_talk", "Push-to-Talk (hold to record)"),
            ("toggle", "Toggle (press to start/stop)"),
        ):
            act = QAction(label, mode_menu)
            act.setCheckable(True)
            act.triggered.connect(
                lambda checked=False, m=mode: self._set_mode(m)
            )
            mode_menu.addAction(act)
            self._mode_actions[mode] = act
        self._refresh_mode_checks()

        lang_menu = self._menu.addMenu("Language (ภาษา)")
        from voice_typing.config.settings import SUPPORTED_LANGUAGES
        for code, label in SUPPORTED_LANGUAGES:
            act = QAction(label, lang_menu)
            act.setCheckable(True)
            act.triggered.connect(
                lambda checked=False, c=code: self._set_language(c)
            )
            lang_menu.addAction(act)
            self._lang_actions[code] = act
        self._refresh_lang_checks()

        history_action = QAction("Open History in Settings", self._menu)
        history_action.triggered.connect(self.signals.open_history.emit)
        self._menu.addAction(history_action)

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

    # ------------------------------------------------------------------
    # Surgical row updates (no full rebuild)
    # ------------------------------------------------------------------

    def _refresh_status_row(self) -> None:
        if self._status_action is None:
            return
        self._status_dot_color = status_dot_color(self._status_text)
        if "Recording" in self._status_text:
            text = "● Recording"
        else:
            text = f"● {self._status_text}"
        self._status_action.setText(text)
        self._status_action.setIcon(
            self._make_dot_icon(self._status_dot_color)
        )

    def _refresh_start_stop_row(self) -> None:
        if self._start_stop_action is None:
            return
        try:
            self._start_stop_action.triggered.disconnect()
        except (RuntimeError, TypeError):
            pass
        if self._recording:
            self._start_stop_action.setText("Stop Recording")
            self._start_stop_action.triggered.connect(
                self.signals.stop_recording.emit
            )
        else:
            self._start_stop_action.setText("Start Recording")
            self._start_stop_action.triggered.connect(
                self.signals.start_recording.emit
            )

    def _refresh_mode_checks(self) -> None:
        for mode, act in self._mode_actions.items():
            act.setChecked(self._mode == mode)

    def _refresh_lang_checks(self) -> None:
        for code, act in self._lang_actions.items():
            act.setChecked(self._language == code)

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh_mode_checks()
        self.signals.mode_changed.emit(mode)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._refresh_mode_checks()

    def _set_language(self, lang: str) -> None:
        self._language = lang
        self._refresh_lang_checks()
        self.signals.language_changed.emit(lang)

    def set_language(self, lang: str) -> None:
        self._language = lang
        self._refresh_lang_checks()

    def set_history(self, items: list[str]) -> None:
        """Deprecated Phase D no-op shim: stores the list, never renders.

        History now lives in the Settings HistoryPanel. Kept so existing
        ``history_changed`` connections (app worker) don't break.
        """
        self._history = list(items or [])
        log.debug("Tray history shim stored (%d item(s))", len(self._history))

    def set_status(self, status: str) -> None:
        # Dot row only — never rebuild the menu here.
        self._status_text = status
        self._refresh_status_row()
        if self._tray is not None:
            self._tray.setToolTip(f"VoiceType - {status}")

    def update_recording_state(self, recording: bool) -> None:
        self._recording = recording
        self._refresh_start_stop_row()
        self.set_status("Recording..." if recording else "Ready")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.signals.show_status_bar.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # Menu is kept current via surgical updates; just pop it up.
            if self._menu is not None:
                self._menu.popup(QCursor.pos())

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()
