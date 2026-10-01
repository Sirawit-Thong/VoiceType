# voice_typing/ui/settings_window.py
"""UX Phase D: settings window with sidebar navigation + background queue.

Layout: sidebar ``QListWidget`` (General / Hotkey / Speech / AI Keys /
History / About) + search filter + ``QStackedWidget`` pages. Existing
page builders are reparented into the stack (all ``self._*`` widget
names preserved).

Decisions (Phase D, pre-approved):
- Search filters page titles only (not individual control labels).
- AI-Keys rows show a per-key status dot (gray untested / amber testing /
  green valid / red invalid) + masked label + ``Key i/n`` index. No GCP
  project API is called — the index is positional, not project-aware.
- History page embeds :class:`HistoryPanel`; history-row selection never
  marks the window dirty (dirty = settings controls only).
- Dirty tracking appends ``*`` to the title; ``Ctrl+S`` saves; closing
  with unsaved changes asks Save / Discard / Cancel.
- API-key tests + model loads run on :class:`WorkerQueue` (single
  QObject-worker + QThread); the old ``_ApiKeyTester`` / ``_ModelLoader``
  chains are removed. ``_LiveMicTester`` stays a local thread.
- Setup wizard is relaunchable from the About page (applies to UI
  controls; saving still goes through Save).
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

from PySide6.QtCore import QEvent, QObject, Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.audio.recorder import list_input_devices
from voice_typing.config.settings import DEFAULT_SETTINGS, SettingsManager, VERSION, RELEASE_URL, get_asset_path
from voice_typing.speech.gemini_live import MODEL
from voice_typing.speech.key_pool import KeyPool
from voice_typing.ui.history_panel import HistoryPanel
from voice_typing.ui.worker_queue import WorkerQueue
from voice_typing.windows.hotkey import HOTKEY_OPTIONS, hotkey_name


# Per-key dot colors: gray untested / amber testing / green valid / red invalid.
_KEY_STATUS_COLORS = {
    "untested": "#9aa0a6",
    "testing": "#fbbc04",
    "valid": "#34a853",
    "invalid": "#ea4335",
}

_PAGE_TITLES = ["General", "Hotkey", "Speech", "AI Keys", "History", "About"]

_BASE_TITLE = "VoiceType Settings"


def _normalize_model(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return MODEL
    return name if name.startswith("models/") else f"models/{name}"


class _LiveMicTester(QThread):
    level_changed = Signal(int)
    finished_test = Signal(bool, str)

    def __init__(self, device_id: int | None = None, duration_sec: float = 5.0) -> None:
        super().__init__()
        self._device_id = device_id
        self._duration_sec = duration_sec
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        import time
        import numpy as np
        import sounddevice as sd

        self._running = True
        sample_rate = 16000
        blocksize = 1600

        def callback(indata, frames, time_info, status):
            if not self._running:
                return
            if indata.dtype == np.int16:
                samples = indata.astype(np.float32) / 32768.0
            else:
                samples = indata.astype(np.float32)
            peak = float(np.max(np.abs(samples))) if len(samples) > 0 else 0.0
            level = int(min(100, max(0, peak * 100)))
            self.level_changed.emit(level)

        try:
            with sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                device=self._device_id,
                callback=callback,
            ):
                start_time = time.time()
                while self._running and (time.time() - start_time < self._duration_sec):
                    time.sleep(0.05)
        except Exception as exc:
            log.warning("Mic test failed: %s", exc)
            self.finished_test.emit(False, f"Mic test failed: {exc}")
        finally:
            self._running = False


class SettingsWindow(QDialog):
    saved = Signal()

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._queue = WorkerQueue(self)
        self._queue.key_tested.connect(self._on_queue_key_tested)
        self._queue.test_all_finished.connect(self._on_queue_test_all_finished)
        self._queue.models_loaded.connect(self._on_models_loaded)
        self._queue.models_failed.connect(self._on_models_failed)
        self._test_all_results: list[tuple[str, bool, str]] = []
        self._key_status: dict[str, str] = {}
        self._mic_tester: _LiveMicTester | None = None
        self._capturing_key = False
        self._capture_timer: QTimer | None = None
        self._dirty = False
        self._populating = False
        self.setWindowTitle(_BASE_TITLE)
        icon_path = get_asset_path("icon.ico")
        if not icon_path.exists():
            icon_path = get_asset_path("icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(640, 440)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #1a1b1e; color: #e8eaed; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: #9aa0a6; font-size: 11px; background: transparent; border: none; }
            QLineEdit { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 10px; font-size: 11px; selection-background-color: #264f78; }
            QLineEdit:focus { border-color: #8ab4f8; }
            QListWidget { background: #212227; border: 1px solid #3c4043; border-radius: 6px; padding: 4px; font-size: 12px; outline: none; }
            QListWidget::item { padding: 8px 10px; border-radius: 4px; }
            QListWidget::item:selected { background: #303134; color: #e8eaed; }
            QListWidget::item:hover { background: #2b2d31; }
            QComboBox { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 10px; font-size: 11px; min-height: 20px; }
            QComboBox:hover { border-color: #5f6368; }
            QComboBox::drop-down { border: none; width: 24px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #9aa0a6; margin-right: 8px; }
            QComboBox QAbstractItemView { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; selection-background-color: #303134; }
            QComboBox:disabled { background: #2b2d31; color: #5f6368; border: 1px solid #3c4043; }
            QCheckBox { color: #e8eaed; spacing: 8px; font-size: 11px; background: transparent; border: none; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1.5px solid #5f6368; background: transparent; }
            QCheckBox::indicator:hover { border-color: #8ab4f8; }
            QCheckBox::indicator:checked { background: #8ab4f8; border-color: #8ab4f8; }
            QCheckBox::indicator:checked:hover { background: #aecbfa; border-color: #aecbfa; }
            QCheckBox:disabled { color: #5f6368; }
            QCheckBox:disabled::indicator { border-color: #3c4043; }
            QSlider::groove:horizontal { background: #3c4043; height: 4px; border-radius: 2px; }
            QSlider::handle:horizontal { background: #8ab4f8; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
            QSlider::handle:horizontal:hover { background: #aecbfa; }
            QSlider::sub-page:horizontal { background: #8ab4f8; border-radius: 2px; }
            QPushButton { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; font-size: 11px; min-height: 20px; }
            QPushButton:hover { background: #383a40; border-color: #5f6368; }
            QPushButton:pressed { background: #4e525a; }
            QPushButton:disabled { background: #2b2d31; color: #5f6368; border: 1px solid #3c4043; }
            QPushButton#primaryBtn { background: #8ab4f8; color: #1a1b1e; border: none; font-weight: bold; }
            QPushButton#primaryBtn:hover { background: #aecbfa; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: #3c4043; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #5f6368; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QMessageBox { background: #1a1b1e; }
            QMessageBox QLabel { color: #e8eaed; }
            QMessageBox QPushButton { background: #2b2d31; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; }
            QMessageBox QPushButton:hover { background: #383a40; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)

        body = QHBoxLayout()
        body.setSpacing(10)

        side = QVBoxLayout()
        side.setSpacing(6)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search settings…")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._filter_sidebar)
        side.addWidget(self._search_box)

        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(150)
        for title in _PAGE_TITLES:
            self._sidebar.addItem(title)
        self._sidebar.setCurrentRow(0)
        self._sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        side.addWidget(self._sidebar, 1)
        body.addLayout(side)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._general_tab())
        self._stack.addWidget(self._hotkey_tab())
        self._stack.addWidget(self._speech_tab())
        self._stack.addWidget(self._ai_keys_tab())
        self._stack.addWidget(self._history_tab())
        self._stack.addWidget(self._about_tab())
        body.addWidget(self._stack, 1)

        layout.addLayout(body, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #9aa0a6; border: 1px solid #3c4043; border-radius: 6px; padding: 6px 16px; font-size: 11px; }
            QPushButton:hover { background: #383a40; border-color: #5f6368; }
        """)
        cancel_btn.clicked.connect(self.close)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryBtn")
        save_btn.setStyleSheet("""
            QPushButton { background: #8ab4f8; color: #1a1b1e; border: none; border-radius: 6px; padding: 6px 20px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background: #aecbfa; }
        """)
        save_btn.clicked.connect(self._save_and_close)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self._save_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        self._save_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._save_shortcut.activated.connect(self._save_and_close)

        self._populating = True
        try:
            self._populate_ui_from_settings()
        finally:
            self._populating = False
        self._set_dirty(False)
        self._wire_dirty_tracking()

    # -- sidebar -----------------------------------------------------------
    def _on_sidebar_row_changed(self, row: int) -> None:
        if 0 <= row < self._stack.count():
            self._stack.setCurrentIndex(row)

    def select_page(self, title: str) -> bool:
        """Select a sidebar page by title (case-insensitive)."""
        needle = (title or "").strip().lower().replace("-", " ").replace("/", " ")
        for i in range(self._sidebar.count()):
            item = self._sidebar.item(i)
            if item is None:
                continue
            label = item.text().lower().replace("-", " ").replace("/", " ")
            if label == needle or needle in label or label in needle:
                self._sidebar.setCurrentRow(i)
                return True
        return False

    def _filter_sidebar(self, text: str) -> None:
        """Filter sidebar rows by page title only (not control labels)."""
        needle = (text or "").strip().lower()
        for i in range(self._sidebar.count()):
            item = self._sidebar.item(i)
            if item is None:
                continue
            self._sidebar.setRowHidden(i, bool(needle) and needle not in item.text().lower())
        # Keep a visible page selected.
        current = self._sidebar.currentRow()
        if current >= 0 and self._sidebar.isRowHidden(current):
            for i in range(self._sidebar.count()):
                if not self._sidebar.isRowHidden(i):
                    self._sidebar.setCurrentRow(i)
                    break

    # -- dirty tracking ------------------------------------------------------
    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        self.setWindowTitle(_BASE_TITLE + ("*" if self._dirty else ""))

    def _mark_dirty(self) -> None:
        if self._populating:
            return
        self._set_dirty(True)

    def _wire_dirty_tracking(self) -> None:
        mark = lambda *a: self._mark_dirty()
        for combo in (
            self._mode_combo, self._capsule_style_combo, self._hotkey_combo,
            self._lang_combo, self._mic_combo, self._model_combo,
            self._overlay_font_combo,
        ):
            combo.currentIndexChanged.connect(mark)
        for check in (
            self._start_windows, self._show_status, self._sound_feedback,
            self._copy_to_clipboard, self._overlay_enabled, self._fast_mode,
        ):
            check.toggled.connect(mark)
        for slider in (
            self._opacity_slider, self._speed_slider, self._sensitivity_slider,
            self._overlay_opacity_slider, self._overlay_dismiss_slider,
        ):
            slider.valueChanged.connect(mark)
        self._overlay_max_height_spin.valueChanged.connect(mark)
        self._custom_vocab.textChanged.connect(mark)
        self._api_key_input.textChanged.connect(mark)
        try:
            model = self._api_keys_list.model()
            model.rowsInserted.connect(mark)
            model.rowsRemoved.connect(mark)
        except Exception:
            pass
        # History selection is intentionally NOT wired (dirty = settings only).

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3c4043;")
        return sep

    def _general_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Push-to-Talk (hold key to record)", "push_to_talk")
        self._mode_combo.addItem("Toggle (press once to start/stop)", "toggle")
        layout.addRow("Recording Mode:", self._mode_combo)

        self._capsule_style_combo = QComboBox()
        self._capsule_style_combo.addItem("Dynamic Pill (always visible oval)", "pill")
        self._capsule_style_combo.addItem("Ultra-Minimal Dot (expands on speech/hover)", "dot")
        layout.addRow("Capsule Style:", self._capsule_style_combo)

        opacity_layout = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_label = QLabel()
        self._opacity_slider.valueChanged.connect(lambda v: self._opacity_label.setText(f"{v}%"))
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        layout.addRow("Capsule Opacity:", opacity_layout)

        self._start_windows = QCheckBox()
        layout.addRow("Start with Windows:", self._start_windows)

        self._show_status = QCheckBox()
        layout.addRow("Show floating status bar:", self._show_status)

        sound_layout = QHBoxLayout()
        self._sound_feedback = QCheckBox()
        self._test_sound_btn = QPushButton("🔊 Test Beep")
        self._test_sound_btn.clicked.connect(self._play_test_beep)
        sound_layout.addWidget(self._sound_feedback)
        sound_layout.addWidget(self._test_sound_btn)
        sound_layout.addStretch()
        layout.addRow("Sound feedback (beeps):", sound_layout)

        self._copy_to_clipboard = QCheckBox("Also copy recognized text to clipboard")
        layout.addRow("Clipboard:", self._copy_to_clipboard)

        # -- Transcript Overlay section ------------------------------------------
        layout.addRow("", self._make_separator())
        overlay_title = QLabel("Transcript Overlay")
        overlay_title.setStyleSheet(
            "color: #e8eaed; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addRow("", overlay_title)

        self._overlay_enabled = QCheckBox("Show live transcript overlay")
        layout.addRow("", self._overlay_enabled)

        overlay_opacity_layout = QHBoxLayout()
        self._overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._overlay_opacity_slider.setRange(50, 100)
        self._overlay_opacity_label = QLabel()
        self._overlay_opacity_slider.valueChanged.connect(
            lambda v: self._overlay_opacity_label.setText(f"{v}%")
        )
        overlay_opacity_layout.addWidget(self._overlay_opacity_slider)
        overlay_opacity_layout.addWidget(self._overlay_opacity_label)
        layout.addRow("Overlay Opacity:", overlay_opacity_layout)

        self._overlay_font_combo = QComboBox()
        self._overlay_font_combo.addItem("Small (11px)", 11)
        self._overlay_font_combo.addItem("Medium (13px)", 13)
        self._overlay_font_combo.addItem("Large (16px)", 16)
        layout.addRow("Overlay Font Size:", self._overlay_font_combo)

        # M4: max-height binds the existing overlay_max_height key (100-600px).
        # Pin + geometry are intentionally NOT exposed here — they are
        # overlay-signal-owned (pin_toggled/geometry_changed persist to
        # settings via the overlay title-bar + drag/resize, no manual UI).
        self._overlay_max_height_spin = QSpinBox()
        self._overlay_max_height_spin.setRange(100, 600)
        self._overlay_max_height_spin.setSingleStep(10)
        self._overlay_max_height_spin.setSuffix(" px")
        layout.addRow("Overlay Max Height:", self._overlay_max_height_spin)

        overlay_dismiss_layout = QHBoxLayout()
        self._overlay_dismiss_slider = QSlider(Qt.Orientation.Horizontal)
        self._overlay_dismiss_slider.setRange(1, 10)
        self._overlay_dismiss_slider.setSingleStep(1)
        self._overlay_dismiss_label = QLabel()
        self._overlay_dismiss_slider.valueChanged.connect(
            lambda v: self._overlay_dismiss_label.setText(
                f"{v} {'sec' if v == 1 else 'secs'}"
            )
        )
        overlay_dismiss_layout.addWidget(self._overlay_dismiss_slider)
        overlay_dismiss_layout.addWidget(self._overlay_dismiss_label)
        layout.addRow("Auto-Dismiss Delay:", overlay_dismiss_layout)

        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._hotkey_combo = QComboBox()
        layout.addRow("Voice Typing Key / Button:", self._hotkey_combo)

        self._capture_btn = QPushButton("🎮  Press a key or mouse button to capture")
        self._capture_btn.clicked.connect(self._start_key_capture)
        layout.addRow("", self._capture_btn)

        hint = QLabel(
            "Push-to-Talk: hold the key/mouse button to record, release to type.\n"
            "Toggle: press once to start, press again to stop."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")

        keys_hint = QLabel(
            "Supported keys: F6-F12, CapsLock, and mouse side buttons / middle click."
        )
        keys_hint.setWordWrap(True)
        keys_hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        layout.addRow("", hint)
        layout.addRow("", keys_hint)

        return w

    def _speech_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Auto (Thai + English)", "Thai (ภาษาไทย)", "English"])
        layout.addRow("Language:", self._lang_combo)

        mic_layout = QHBoxLayout()
        self._mic_combo = QComboBox()
        refresh_btn = QPushButton("↺")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self._refresh_mics)
        mic_layout.addWidget(self._mic_combo, 1)
        mic_layout.addWidget(refresh_btn)
        layout.addRow("Microphone:", mic_layout)

        mic_level_layout = QHBoxLayout()
        self._mic_level_bar = QProgressBar()
        self._mic_level_bar.setRange(0, 100)
        self._mic_level_bar.setValue(0)
        self._mic_level_bar.setTextVisible(True)
        self._test_mic_btn = QPushButton("🎤 Test Mic")
        self._test_mic_btn.clicked.connect(self._toggle_mic_test)
        mic_level_layout.addWidget(self._mic_level_bar, 1)
        mic_level_layout.addWidget(self._test_mic_btn)
        layout.addRow("Audio Level:", mic_level_layout)

        speed_layout = QHBoxLayout()
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(0, 5)
        self._speed_slider.setSingleStep(1)
        self._speed_label = QLabel()
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText("Instant" if v == 0 else f"{v} ms/char")
        )
        speed_layout.addWidget(self._speed_slider)
        speed_layout.addWidget(self._speed_label)
        layout.addRow("Typing Speed:", speed_layout)

        sensitivity_layout = QHBoxLayout()
        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self._sensitivity_slider.setRange(1, 20)
        self._sensitivity_slider.setSingleStep(1)
        self._sensitivity_label = QLabel()
        self._sensitivity_slider.valueChanged.connect(self._update_sensitivity_label)
        sensitivity_layout.addWidget(self._sensitivity_slider)
        sensitivity_layout.addWidget(self._sensitivity_label)
        layout.addRow("Voice Sensitivity:", sensitivity_layout)

        return w

    def _update_sensitivity_label(self, v: int) -> None:
        if v <= 5:
            text = "Low"
        elif v <= 13:
            text = "Medium"
        else:
            text = "High"
        self._sensitivity_label.setText(text)

    def _ai_keys_tab(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(12)
        layout.setContentsMargins(12, 8, 12, 8)

        # Multi-key list (masked display + per-key dot + index, full key in UserRole).
        self._api_keys_list = QListWidget()
        self._api_keys_list.setMaximumHeight(110)
        layout.addRow("API Keys:", self._api_keys_list)

        # Add row: new-key input + Add button.
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Paste a new Gemini API key")
        self._add_key_btn = QPushButton("Add")
        self._add_key_btn.clicked.connect(self._add_api_key)
        add_layout = QHBoxLayout()
        add_layout.addWidget(self._api_key_input, 1)
        add_layout.addWidget(self._add_key_btn)
        layout.addRow("", add_layout)

        # Backward compat: legacy single-field tests use ``_api_key``.
        self._api_key = self._api_key_input

        # Remove / Test / Test-All row + status dot.
        self._api_status = QLabel("● Not tested")
        self._api_status.setObjectName("api_status")
        self._api_status.setStyleSheet("color: #9aa0a6; font-size: 16px;")

        self._test_key_btn = QPushButton("Test Key")
        self._test_key_btn.clicked.connect(self._test_api_key)
        self._test_all_btn = QPushButton("Test All")
        self._test_all_btn.clicked.connect(self._test_all_keys)
        self._remove_key_btn = QPushButton("Remove")
        self._remove_key_btn.clicked.connect(self._remove_selected_api_key)

        key_btn_layout = QHBoxLayout()
        key_btn_layout.addWidget(self._api_status)
        key_btn_layout.addStretch()
        key_btn_layout.addWidget(self._test_key_btn)
        key_btn_layout.addWidget(self._test_all_btn)
        key_btn_layout.addWidget(self._remove_key_btn)
        layout.addRow("", key_btn_layout)

        self._quota_label = QLabel(
            "Keys from same Google Cloud Project share quota — "
            "use keys from different projects/accounts for failover."
        )
        self._quota_label.setWordWrap(True)
        self._quota_label.setStyleSheet("color: #fbbc04; font-size: 10px;")
        layout.addRow("", self._quota_label)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(False)
        self._load_models_btn = QPushButton("Load models")
        self._load_models_btn.clicked.connect(self._load_models)

        model_layout = QHBoxLayout()
        model_layout.addWidget(self._model_combo, 1)
        model_layout.addWidget(self._load_models_btn)
        layout.addRow("Model:", model_layout)

        self._fast_mode = QCheckBox()
        layout.addRow("Fast Mode:", self._fast_mode)

        hint = QLabel("Skip AI punctuation correction for faster real-time response.")
        hint.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        self._custom_vocab = QLineEdit()
        self._custom_vocab.setPlaceholderText("e.g., Python, PySide6, Gemini, Prompt engineering")
        layout.addRow("Custom Vocabulary / Keywords:", self._custom_vocab)

        vocab_help = QLabel(
            "Add specific words, names, or jargon to help Gemini recognize them accurately."
        )
        vocab_help.setStyleSheet("color: #9aa0a6; font-size: 10px;")
        vocab_help.setWordWrap(True)
        layout.addRow("", vocab_help)

        vocab_warning = QLabel(
            "⚠ Note: Requires \"Fast Mode\" to be OFF to take effect."
        )
        vocab_warning.setStyleSheet("color: #fbbc04; font-size: 10px;")
        vocab_warning.setWordWrap(True)
        layout.addRow("", vocab_warning)

        return w

    # Compat alias: pre-rename name kept for tests/callers.
    _gemini_tab = _ai_keys_tab

    def _history_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(12, 8, 12, 8)
        hint = QLabel("Recent dictations (newest first). Select an item, then Copy or Re-inject.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.history_panel = HistoryPanel()
        layout.addWidget(self.history_panel, 1)
        return w

    def _about_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_label = QLabel()
        icon_path = get_asset_path("icon.png")
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(
                80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignCenter)

        title = QLabel("VoiceType")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e8eaed; margin-top: 8px;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f'<a href="{RELEASE_URL}" style="color: #8ab4f8; font-size: 12px; text-decoration: none;">v{VERSION}</a>')
        version.setOpenExternalLinks(True)
        version.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(version, 0, Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Real-time Thai + English voice-to-text for Windows")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #9aa0a6; margin-top: 8px; font-size: 12px;")
        layout.addWidget(desc, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        get_key_btn = QPushButton("🔑  Get Gemini API Key")
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #8ab4f8; border: none; font-size: 12px; text-decoration: underline;
            }
            QPushButton:hover {
                color: #aecbfa;
            }
        """)
        get_key_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://aistudio.google.com/apikey")))
        layout.addWidget(get_key_btn, 0, Qt.AlignmentFlag.AlignCenter)

        self._wizard_btn = QPushButton("🧙  Run Setup Wizard…")
        self._wizard_btn.clicked.connect(self._open_setup_wizard)
        layout.addWidget(self._wizard_btn, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #3c4043;")
        layout.addWidget(sep)

        reset_btn = QPushButton("⚠️  Reset All Settings to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #2b1a1a; color: #ea4335; border: 1px solid #ea4335; border-radius: 6px; padding: 6px 16px; font-size: 11px; font-weight: 500;
            }
            QPushButton:hover { background: #3d1a1a; }
        """)
        reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(reset_btn, 0, Qt.AlignmentFlag.AlignCenter)

        return w

    def _open_setup_wizard(self) -> None:
        """Relaunch the setup wizard; apply accepted results to UI controls."""
        from voice_typing.ui.setup_wizard import SetupWizard

        wiz = SetupWizard(self)
        if wiz.exec() != QDialog.DialogCode.Accepted:
            return
        keys = wiz.keys()
        if keys:
            self._refresh_keys_list(keys)
        from voice_typing.config.settings import LANGUAGE_INDEX
        self._lang_combo.setCurrentIndex(LANGUAGE_INDEX.get(wiz.language(), 0))
        vk = wiz.hotkey()
        found = -1
        for i in range(self._hotkey_combo.count()):
            if self._hotkey_combo.itemData(i) == vk:
                found = i
                break
        if found == -1:
            self._hotkey_combo.addItem(hotkey_name(vk), vk)
            found = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(found)
        self._refresh_mics()
        mic_id = wiz.microphone_device_id()
        for i in range(self._mic_combo.count()):
            if self._mic_combo.itemData(i) == mic_id:
                self._mic_combo.setCurrentIndex(i)
                break
        self._mark_dirty()

    def _play_test_beep(self) -> None:
        def _beep():
            try:
                import winsound
                winsound.Beep(1000, 150)
            except Exception:
                pass

        import threading
        threading.Thread(target=_beep, daemon=True).start()

    def _toggle_mic_test(self) -> None:
        if self._mic_tester is not None and self._mic_tester.isRunning():
            self._stop_mic_test()
        else:
            self._start_mic_test()

    def _start_mic_test(self) -> None:
        device_id = self._mic_combo.currentData()
        self._test_mic_btn.setText("⏹ Stop Test")
        self._mic_tester = _LiveMicTester(device_id=device_id)
        self._mic_tester.level_changed.connect(self._mic_level_bar.setValue)
        self._mic_tester.finished.connect(self._on_mic_test_finished)
        self._mic_tester.finished_test.connect(self._on_mic_test_finished)
        self._mic_tester.start()

    def _stop_mic_test(self) -> None:
        if self._mic_tester is not None:
            self._mic_tester.stop()
            self._mic_tester.wait(500)
        self._on_mic_test_finished()

    def _on_mic_test_finished(self, success: bool = True, msg: str = "") -> None:
        self._test_mic_btn.setText("🎤 Test Mic")
        self._mic_level_bar.setValue(0)
        if not success and msg:
            QMessageBox.warning(self, "Mic Test Error", msg)
        self._mic_tester = None

    def closeEvent(self, event) -> None:
        if self._capturing_key:
            self._cancel_key_capture()
        if self._mic_tester is not None:
            tester = self._mic_tester
            for _sig in ("finished", "finished_test"):
                try:
                    getattr(tester, _sig).disconnect()
                except (RuntimeError, TypeError):
                    pass
                except Exception:
                    pass
            try:
                tester.stop()
            except Exception:
                pass
            try:
                if tester.isRunning():
                    tester.wait(300)
            except Exception:
                pass
            self._mic_tester = None
            try:
                self._test_mic_btn.setText("🎤 Test Mic")
            except Exception:
                pass
            try:
                self._mic_level_bar.setValue(0)
            except Exception:
                pass
        # Unsaved-changes confirm BEFORE tearing down the worker queue so
        # Cancel keeps background work alive.
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_settings()
                self._set_dirty(False)
            elif reply == QMessageBox.StandardButton.Discard:
                pass
            else:
                event.ignore()
                return
        # Close-safe worker teardown: cancel + disconnect + wait
        # (offscreen-safe, no QMessageBox here).
        try:
            self._queue.shutdown()
        except Exception:
            pass
        try:
            self._load_models_btn.setEnabled(True)
            self._load_models_btn.setText("Load models")
        except Exception:
            pass
        try:
            self._test_key_btn.setEnabled(True)
            self._test_key_btn.setText("Test Key")
        except Exception:
            pass
        try:
            self._test_all_btn.setEnabled(True)
            self._test_all_btn.setText("Test All")
        except Exception:
            pass
        super().closeEvent(event)

    def _populate_ui_from_settings(self) -> None:
        # General
        mode = self._settings.get("mode", "push_to_talk")
        self._mode_combo.setCurrentIndex(0 if mode == "push_to_talk" else 1)

        style = self._capsule_style_combo.findData(self._settings.get("capsule_style", "pill"))
        self._capsule_style_combo.setCurrentIndex(max(0, style))

        opacity_val = int(self._settings.get("opacity", 0.94) * 100)
        self._opacity_slider.setValue(opacity_val)
        self._opacity_label.setText(f"{self._opacity_slider.value()}%")

        self._start_windows.setChecked(self._settings.get("start_with_windows", False))
        self._show_status.setChecked(self._settings.get("show_status_bar", True))
        self._sound_feedback.setChecked(self._settings.get("sound_feedback", True))
        self._copy_to_clipboard.setChecked(self._settings.get("copy_to_clipboard", False))

        # Overlay
        self._overlay_enabled.setChecked(self._settings.get("overlay_enabled", True))
        overlay_opacity_val = int(self._settings.get("overlay_opacity", 0.92) * 100)
        self._overlay_opacity_slider.setValue(overlay_opacity_val)
        self._overlay_opacity_label.setText(f"{self._overlay_opacity_slider.value()}%")

        overlay_font = self._settings.get("overlay_font_size", 13)
        font_idx = self._overlay_font_combo.findData(overlay_font)
        if font_idx >= 0:
            self._overlay_font_combo.setCurrentIndex(font_idx)
        else:
            self._overlay_font_combo.setCurrentIndex(1)  # Default to Medium

        dismiss_val = int(self._settings.get("overlay_auto_dismiss_seconds", 3))
        self._overlay_dismiss_slider.setValue(dismiss_val)
        self._overlay_dismiss_label.setText(
            f"{dismiss_val} {'sec' if dismiss_val == 1 else 'secs'}"
        )

        # M4 round-trip: clamp existing key into spin range.
        try:
            _mh = int(self._settings.get("overlay_max_height", 300))
        except (TypeError, ValueError):
            _mh = 300
        self._overlay_max_height_spin.setValue(max(100, min(600, _mh)))

        # Hotkey
        current_hotkey = self._settings.get("hotkey", 0x78)
        self._hotkey_combo.clear()
        selected = 0
        for i, (name, code) in enumerate(HOTKEY_OPTIONS):
            self._hotkey_combo.addItem(name, code)
            if code == current_hotkey:
                selected = i
        if self._hotkey_combo.itemData(selected) != current_hotkey:
            self._hotkey_combo.addItem(hotkey_name(current_hotkey), current_hotkey)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)

        # Speech
        current_lang = self._settings.get("language", "auto")
        from voice_typing.config.settings import LANGUAGE_INDEX
        idx = LANGUAGE_INDEX.get(current_lang, 0)
        self._lang_combo.setCurrentIndex(idx)

        self._refresh_mics()
        current_mic = self._settings.get("microphone_device_id")
        mic_selected = 0
        for i in range(self._mic_combo.count()):
            if self._mic_combo.itemData(i) == current_mic:
                mic_selected = i
                break
        self._mic_combo.setCurrentIndex(mic_selected)

        speed_val = self._settings.get("typing_speed", 0)
        self._speed_slider.setValue(speed_val)
        v_spd = self._speed_slider.value()
        self._speed_label.setText("Instant" if v_spd == 0 else f"{v_spd} ms/char")

        sens_val = int(self._settings.get("silence_threshold", 0.005) * 1000)
        self._sensitivity_slider.setValue(sens_val)
        self._update_sensitivity_label(self._sensitivity_slider.value())

        # Gemini
        get_keys = getattr(self._settings, "get_api_keys", None)
        if callable(get_keys):
            try:
                stored_keys = list(get_keys())
            except Exception:
                stored_keys = []
        else:
            stored_keys = list(self._settings.get("api_keys", []) or [])
        if not stored_keys:
            legacy = self._settings.get("api_key", "") or ""
            if isinstance(legacy, str) and legacy.strip():
                stored_keys = [legacy.strip()]
        self._refresh_keys_list(stored_keys)
        self._api_key_input.clear()
        self._api_status.setText("● Not tested")
        self._api_status.setStyleSheet("color: #9aa0a6; font-size: 16px;")

        current_model = _normalize_model(self._settings.get("model", MODEL))
        self._model_combo.clear()
        self._model_combo.addItem(current_model, current_model)
        self._model_combo.setCurrentIndex(0)

        self._fast_mode.setChecked(self._settings.get("fast_mode", True))
        self._custom_vocab.setText(self._settings.get("custom_vocabulary", ""))

    def _refresh_mics(self) -> None:
        current = self._mic_combo.currentData()
        self._mic_combo.clear()
        self._mic_combo.addItem("Default Microphone", None)
        try:
            for index, name in list_input_devices():
                self._mic_combo.addItem(name, index)
        except Exception:
            pass

        selected = 0
        if current is not None:
            for i in range(self._mic_combo.count()):
                if self._mic_combo.itemData(i) == current:
                    selected = i
                    break
        self._mic_combo.setCurrentIndex(selected)

    def _start_key_capture(self) -> None:
        self._capturing_key = True
        self._capture_btn.setText("⏳  Listening... (press key/mouse, Esc to cancel)")
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.installEventFilter(self)
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
        self._capture_timer = QTimer(self)
        self._capture_timer.setSingleShot(True)
        self._capture_timer.timeout.connect(self._cancel_key_capture)
        self._capture_timer.start(5000)

    def _cancel_key_capture(self) -> None:
        self._capturing_key = False
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.removeEventFilter(self)
        if self._capture_timer is not None:
            self._capture_timer.stop()
            self._capture_timer.deleteLater()
            self._capture_timer = None
        self._capture_btn.setText("🎮  Press a key or mouse button to capture")

    def _apply_captured_vk(self, vk: int) -> None:
        selected = -1
        for i in range(self._hotkey_combo.count()):
            if self._hotkey_combo.itemData(i) == vk:
                selected = i
                break
        if selected == -1:
            name = hotkey_name(vk)
            self._hotkey_combo.addItem(name, vk)
            selected = self._hotkey_combo.count() - 1
        self._hotkey_combo.setCurrentIndex(selected)
        self._cancel_key_capture()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._capturing_key and event.type() == QEvent.Type.MouseButtonPress:
            btn = event.button()
            vk = 0
            if btn == Qt.MouseButton.MiddleButton:
                vk = 0x04
            elif btn in (Qt.MouseButton.BackButton, Qt.MouseButton.XButton1):
                vk = 0x05
            elif btn in (Qt.MouseButton.ForwardButton, Qt.MouseButton.XButton2):
                vk = 0x06
            if vk > 0:
                self._apply_captured_vk(vk)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self._capturing_key:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel_key_capture()
                event.accept()
                return
            vk = event.nativeVirtualKey()
            if vk > 0:
                self._apply_captured_vk(vk)
                event.accept()
                return
        super().keyPressEvent(event)

    # -- Multi-key helpers -------------------------------------------------
    def _refresh_keys_list(self, keys: list[str], reset_status: bool = False) -> None:
        """Rebuild the key list with per-key dot + masked label + index.

        Statuses survive add/remove (keyed by full key); ``reset_status``
        clears them back to untested.
        """
        keys = KeyPool.normalize_keys(keys)
        if reset_status:
            self._key_status = {}
        for k in keys:
            self._key_status.setdefault(k, "untested")
        for k in list(self._key_status):
            if k not in set(keys):
                del self._key_status[k]
        self._api_keys_list.clear()
        n = len(keys)
        for i, k in enumerate(keys):
            status = self._key_status.get(k, "untested")
            item = QListWidgetItem(f"● {KeyPool.mask(k)}  (Key {i + 1}/{n})")
            item.setData(Qt.ItemDataRole.UserRole, k)
            item.setForeground(QColor(_KEY_STATUS_COLORS.get(status, "#9aa0a6")))
            self._api_keys_list.addItem(item)

    def _set_key_status(self, key: str, status: str) -> None:
        self._key_status[key] = status
        n = self._api_keys_list.count()
        for i in range(n):
            item = self._api_keys_list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == key:
                item.setText(f"● {KeyPool.mask(key)}  (Key {i + 1}/{n})")
                item.setForeground(QColor(_KEY_STATUS_COLORS.get(status, "#9aa0a6")))
                break

    def _collect_keys_from_ui(self, raw: bool = False) -> list[str]:
        keys: list[str] = []
        for i in range(self._api_keys_list.count()):
            item = self._api_keys_list.item(i)
            if item is None:
                continue
            full = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(full, str) and full.strip():
                keys.append(full.strip())
        if not raw:
            # Include un-added input text so legacy single-field flows still save.
            pending = self._api_key_input.text().strip()
            if pending and pending not in keys:
                keys.append(pending)
        return KeyPool.normalize_keys(keys)

    def _selected_or_first_key(self) -> str:
        selected = self._api_keys_list.selectedItems()
        if selected:
            full = selected[0].data(Qt.ItemDataRole.UserRole)
            if isinstance(full, str) and full.strip():
                return full.strip()
        for i in range(self._api_keys_list.count()):
            item = self._api_keys_list.item(i)
            if item is not None:
                full = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(full, str) and full.strip():
                    return full.strip()
        return ""

    def _effective_single_key(self) -> str:
        typed = self._api_key_input.text().strip()
        if typed:
            return typed
        return self._selected_or_first_key()

    def _add_api_key(self) -> None:
        raw = self._api_key_input.text().strip()
        if not raw:
            return
        normalized = self._collect_keys_from_ui()
        self._refresh_keys_list(normalized)
        # Keep selection on the newly added key.
        for i in range(self._api_keys_list.count()):
            item = self._api_keys_list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == raw:
                self._api_keys_list.setCurrentRow(i)
                break
        self._api_key_input.clear()

    def _remove_selected_api_key(self) -> None:
        selected = self._api_keys_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Select an API key to remove.")
            return
        for item in selected:
            # takeItem() transfers ownership to the caller; in PySide6 the
            # returned wrapper must be released (no deleteLater — QListWidgetItem
            # is not a QObject) or the C++ item leaks.
            taken = self._api_keys_list.takeItem(self._api_keys_list.row(item))
            del taken
        # Prune statuses + re-index remaining rows.
        remaining = self._collect_keys_from_ui(raw=True)
        self._refresh_keys_list(remaining)

    # -- WorkerQueue-driven test / load ---------------------------------------
    def _set_api_busy(self, busy: bool, what: str = "") -> None:
        self._test_key_btn.setEnabled(not busy)
        self._test_all_btn.setEnabled(not busy)
        if busy:
            self._api_status.setText("● Testing...")
            self._api_status.setStyleSheet("color: #fbbc04; font-size: 16px;")
            if what == "key":
                self._test_key_btn.setText("Testing...")
            elif what == "all":
                self._test_all_btn.setText("Testing...")

    def _test_api_key(self) -> None:
        api_key = self._effective_single_key()
        if not api_key:
            QMessageBox.warning(self, "API Key Required", "Enter an API Key to test.")
            return
        self._set_key_status(api_key, "testing")
        self._set_api_busy(True, "key")
        self._test_key_btn.setText("Testing...")
        self._queue.test_key(api_key)

    def _on_queue_key_tested(self, key: str, success: bool, msg: str) -> None:
        self._test_key_btn.setEnabled(True)
        self._test_key_btn.setText("Test Key")
        self._test_all_btn.setEnabled(True)
        self._set_key_status(key, "valid" if success else "invalid")
        if success:
            self._api_status.setText("● Valid")
            self._api_status.setStyleSheet("color: #34a853; font-size: 16px;")
            QMessageBox.information(self, "API Key Test", msg)
        else:
            self._api_status.setText("● Invalid")
            self._api_status.setStyleSheet("color: #ea4335; font-size: 16px;")
            QMessageBox.warning(self, "API Key Test", msg)

    def _test_all_keys(self) -> None:
        keys = self._collect_keys_from_ui()
        if not keys:
            QMessageBox.warning(self, "API Key Required", "Add at least one API Key to test.")
            return
        for k in keys:
            self._set_key_status(k, "testing")
        self._set_api_busy(True, "all")
        self._test_all_btn.setText("Testing...")
        self._queue.test_all(keys)

    def _on_queue_test_all_finished(self, results: list) -> None:
        self._test_all_results = list(results)
        self._test_all_btn.setEnabled(True)
        self._test_all_btn.setText("Test All")
        self._test_key_btn.setEnabled(True)
        self._test_key_btn.setText("Test Key")
        for k, ok, _ in self._test_all_results:
            self._set_key_status(k, "valid" if ok else "invalid")
        ok = sum(1 for _, s, _ in self._test_all_results if s)
        total = len(self._test_all_results)
        if total and ok == total:
            self._api_status.setText("● Valid")
            self._api_status.setStyleSheet("color: #34a853; font-size: 16px;")
        elif ok:
            self._api_status.setText("● Partial")
            self._api_status.setStyleSheet("color: #fbbc04; font-size: 16px;")
        else:
            self._api_status.setText("● Invalid")
            self._api_status.setStyleSheet("color: #ea4335; font-size: 16px;")
        lines = [
            f"{KeyPool.mask(k)}: {'OK' if s else 'FAIL'}"
            for k, s, _ in self._test_all_results
        ]
        summary = f"{ok}/{total} keys valid.\n" + "\n".join(lines)
        if ok == total:
            QMessageBox.information(self, "API Key Test", summary)
        else:
            QMessageBox.warning(self, "API Key Test", summary)

    def _load_models(self) -> None:
        api_key = self._effective_single_key()
        if not api_key:
            QMessageBox.warning(
                self, "API Key Required", "Enter your Gemini API key first."
            )
            return
        self._load_models_btn.setEnabled(False)
        self._load_models_btn.setText("Loading...")
        self._queue.load_models(api_key)

    def _on_models_loaded(self, models: list) -> None:
        self._load_models_btn.setEnabled(True)
        self._load_models_btn.setText("Load models")
        current = _normalize_model(self._settings.get("model", MODEL))
        self._model_combo.clear()
        selected = 0
        for i, name in enumerate(models):
            norm_name = _normalize_model(name)
            self._model_combo.addItem(norm_name, norm_name)
            if norm_name == current:
                selected = i
        if self._model_combo.count() == 0 or self._model_combo.itemData(selected) != current:
            self._model_combo.addItem(f"Custom: {current}", current)
            selected = self._model_combo.count() - 1
        self._model_combo.setCurrentIndex(selected)

    def _on_models_failed(self, reason: str) -> None:
        self._load_models_btn.setEnabled(True)
        self._load_models_btn.setText("Load models")
        QMessageBox.warning(
            self, "Load Models Failed", f"Could not fetch models:\n{reason[:400]}"
        )

    def _reset_to_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "Reset Settings", "This will reset all settings to defaults. Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for k, v in DEFAULT_SETTINGS.items():
                self._settings.set(k, list(v) if isinstance(v, list) else v)
            self._populating = True
            try:
                self._populate_ui_from_settings()
            finally:
                self._populating = False
            self._mark_dirty()
            QMessageBox.information(self, "Done", "Settings have been reset to defaults.")

    def _save_settings(self) -> None:
        self._settings.set("mode", str(self._mode_combo.currentData()))
        self._settings.set("capsule_style", str(self._capsule_style_combo.currentData()))
        self._settings.set("opacity", self._opacity_slider.value() / 100.0)
        self._settings.set("start_with_windows", self._start_windows.isChecked())
        self._settings.set("show_status_bar", self._show_status.isChecked())
        self._settings.set("sound_feedback", self._sound_feedback.isChecked())
        self._settings.set("copy_to_clipboard", self._copy_to_clipboard.isChecked())
        lang_map = {0: "auto", 1: "thai", 2: "english"}
        self._settings.set("language", lang_map.get(self._lang_combo.currentIndex(), "auto"))
        self._settings.set("microphone_device_id", self._mic_combo.currentData())
        self._settings.set("typing_speed", self._speed_slider.value())
        self._settings.set("silence_threshold", self._sensitivity_slider.value() / 1000.0)
        keys = self._collect_keys_from_ui()
        set_keys = getattr(self._settings, "set_api_keys", None)
        if callable(set_keys):
            set_keys(keys)
        else:
            self._settings.set("api_keys", list(keys))
            self._settings.set("api_key", keys[0] if keys else "")
        model_data = self._model_combo.currentData()
        if model_data is None:
            model_data = self._model_combo.currentText()
        self._settings.set("model", _normalize_model(str(model_data)))
        self._settings.set("fast_mode", self._fast_mode.isChecked())
        self._settings.set("custom_vocabulary", self._custom_vocab.text().strip())
        hotkey_val = self._hotkey_combo.currentData()
        self._settings.set("hotkey", int(hotkey_val) if hotkey_val is not None else 0x78)
        # Overlay settings
        self._settings.set("overlay_enabled", self._overlay_enabled.isChecked())
        self._settings.set(
            "overlay_opacity", self._overlay_opacity_slider.value() / 100.0
        )
        font_data = self._overlay_font_combo.currentData()
        self._settings.set("overlay_font_size", int(font_data) if font_data else 13)
        self._settings.set(
            "overlay_max_height", int(self._overlay_max_height_spin.value())
        )
        self._settings.set(
            "overlay_auto_dismiss_seconds", self._overlay_dismiss_slider.value()
        )

        self._settings.save()
        self.saved.emit()

    def _save_and_close(self) -> None:
        self._save_settings()
        self._set_dirty(False)
        # accept() closes with Accepted; app ignores the exec() result
        # (exec + _settings_win=None unconditionally), so this is safe.
        self.accept()
