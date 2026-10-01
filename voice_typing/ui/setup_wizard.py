# voice_typing/ui/setup_wizard.py
"""UX Phase D: first-run setup wizard (no direct Settings writes).

``QStackedWidget`` flow — 3 setup steps + done page:

1. API keys (multi-key list, masked display, Test All via WorkerQueue).
2. Language + hotkey.
3. Microphone picker + live level test.
4. Done summary.

Accessors (:meth:`keys`, :meth:`language`, :meth:`hotkey`,
:meth:`microphone_device_id`) let the app persist the results; the
wizard itself never touches the settings store. Relaunchable from the
Settings About page (wizard trigger in the app is unchanged: shown only
when no non-blank key is stored).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from voice_typing.audio.recorder import list_input_devices
from voice_typing.config.settings import SUPPORTED_LANGUAGES
from voice_typing.speech.key_pool import KeyPool
from voice_typing.ui.settings_window import _LiveMicTester
from voice_typing.ui.worker_queue import WorkerQueue
from voice_typing.windows.hotkey import HOTKEY_OPTIONS, hotkey_name

log = logging.getLogger(__name__)


class SetupWizard(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VoiceType Setup")
        self.setMinimumSize(460, 380)
        self._queue = WorkerQueue(self)
        self._mic_tester: _LiveMicTester | None = None
        self._test_results: dict[str, bool] = {}
        self._build_ui()

    # -- UI ---------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self._step_label = QLabel()
        self._step_label.setStyleSheet("color: #9aa0a6; font-size: 11px;")
        outer.addWidget(self._step_label)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._keys_page())       # 0
        self._stack.addWidget(self._prefs_page())      # 1
        self._stack.addWidget(self._mic_page())        # 2
        self._stack.addWidget(self._done_page())       # 3
        self._stack.currentChanged.connect(self._refresh_chrome)
        outer.addWidget(self._stack, 1)

        nav = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        self._back_btn = QPushButton("Back")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._cancel_btn)
        nav.addStretch()
        nav.addWidget(self._back_btn)
        nav.addWidget(self._next_btn)
        outer.addLayout(nav)
        self._refresh_chrome()

    # -- page 0: keys -------------------------------------------------------
    def _keys_page(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)

        hint = QLabel("Add one or more Gemini API keys, then Test All.")
        hint.setWordWrap(True)
        layout.addRow("", hint)

        self._keys_list = QListWidget()
        self._keys_list.setMaximumHeight(110)
        layout.addRow("API Keys:", self._keys_list)

        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("Paste a Gemini API key")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_key)
        add_row = QHBoxLayout()
        add_row.addWidget(self._key_input, 1)
        add_row.addWidget(add_btn)
        layout.addRow("", add_row)

        self._keys_status = QLabel("● Not tested")
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_key)
        self._test_all_btn = QPushButton("Test All")
        self._test_all_btn.clicked.connect(self._test_all)
        row = QHBoxLayout()
        row.addWidget(self._keys_status)
        row.addStretch()
        row.addWidget(self._test_all_btn)
        row.addWidget(remove_btn)
        layout.addRow("", row)

        self._queue.test_all_finished.connect(self._on_test_all_finished)
        return w

    # -- page 1: language + hotkey -------------------------------------------
    def _prefs_page(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        self._lang_combo = QComboBox()
        for code, label in SUPPORTED_LANGUAGES:
            self._lang_combo.addItem(label, code)
        layout.addRow("Language:", self._lang_combo)
        self._hotkey_combo = QComboBox()
        for name, code in HOTKEY_OPTIONS:
            self._hotkey_combo.addItem(name, code)
        layout.addRow("Voice Typing Key:", self._hotkey_combo)
        return w

    # -- page 2: microphone ----------------------------------------------------
    def _mic_page(self) -> QWidget:
        w = QWidget()
        layout = QFormLayout(w)
        mic_row = QHBoxLayout()
        self._mic_combo = QComboBox()
        refresh_btn = QPushButton("↺")
        refresh_btn.setFixedWidth(36)
        refresh_btn.clicked.connect(self._refresh_mics)
        mic_row.addWidget(self._mic_combo, 1)
        mic_row.addWidget(refresh_btn)
        layout.addRow("Microphone:", mic_row)

        level_row = QHBoxLayout()
        self._mic_level = QProgressBar()
        self._mic_level.setRange(0, 100)
        self._mic_level.setValue(0)
        self._mic_test_btn = QPushButton("🎤 Test Mic")
        self._mic_test_btn.clicked.connect(self._toggle_mic_test)
        level_row.addWidget(self._mic_level, 1)
        level_row.addWidget(self._mic_test_btn)
        layout.addRow("Audio Level:", level_row)
        self._refresh_mics()
        return w

    # -- page 3: done ------------------------------------------------------------
    def _done_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("You're all set! 🎉")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._summary_label)
        return w

    # -- navigation --------------------------------------------------------------
    def _refresh_chrome(self) -> None:
        idx = self._stack.currentIndex()
        titles = ["Step 1 of 3 — API Keys", "Step 2 of 3 — Language & Hotkey",
                  "Step 3 of 3 — Microphone", "Done"]
        self._step_label.setText(titles[idx])
        self._back_btn.setEnabled(idx > 0 and idx < 3)
        if idx == 3:
            self._update_summary()
            self._next_btn.setText("Finish")
        else:
            self._next_btn.setText("Next")

    def _go_back(self) -> None:
        self._stack.setCurrentIndex(max(0, self._stack.currentIndex() - 1))

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()
        if idx >= 3:
            self.accept()
        else:
            self._stack.setCurrentIndex(idx + 1)

    def _update_summary(self) -> None:
        keys = self.keys()
        masked = ", ".join(KeyPool.mask(k) for k in keys) if keys else "(none)"
        self._summary_label.setText(
            f"Keys: {len(keys)} ({masked})\n"
            f"Language: {self._lang_combo.currentText()}\n"
            f"Hotkey: {hotkey_name(self.hotkey())}"
        )

    # -- keys logic ---------------------------------------------------------------
    def _collect_keys(self) -> list[str]:
        out: list[str] = []
        for i in range(self._keys_list.count()):
            item = self._keys_list.item(i)
            if item is not None:
                full = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(full, str) and full.strip():
                    out.append(full.strip())
        pending = self._key_input.text().strip()
        if pending and pending not in out:
            out.append(pending)
        return KeyPool.normalize_keys(out)

    def _refresh_keys_list(self) -> None:
        current = self._collect_keys()
        self._keys_list.clear()
        for k in current:
            item = QListWidgetItem(KeyPool.mask(k))
            item.setData(Qt.ItemDataRole.UserRole, k)
            self._keys_list.addItem(item)

    def _add_key(self) -> None:
        if not self._key_input.text().strip():
            return
        self._refresh_keys_list()
        self._key_input.clear()

    def _remove_key(self) -> None:
        for item in self._keys_list.selectedItems():
            taken = self._keys_list.takeItem(self._keys_list.row(item))
            del taken

    def _test_all(self) -> None:
        keys = self._collect_keys()
        if not keys:
            QMessageBox.warning(self, "API Key Required", "Add at least one API Key to test.")
            return
        self._test_all_btn.setEnabled(False)
        self._test_all_btn.setText("Testing...")
        self._keys_status.setText("● Testing...")
        self._queue.test_all(keys)

    def _on_test_all_finished(self, results: list) -> None:
        self._test_all_btn.setEnabled(True)
        self._test_all_btn.setText("Test All")
        self._test_results = {k: ok for k, ok, _ in results}
        ok = sum(1 for _, s, _ in results if s)
        total = len(results)
        # Masked logging only.
        log.info("SetupWizard: test-all %d/%d valid", ok, total)
        if total and ok == total:
            self._keys_status.setText("● Valid")
        elif ok:
            self._keys_status.setText("● Partial")
        else:
            self._keys_status.setText("● Invalid")
        lines = [f"{KeyPool.mask(k)}: {'OK' if s else 'FAIL'}" for k, s, _ in results]
        summary = f"{ok}/{total} keys valid.\n" + "\n".join(lines)
        if ok == total:
            QMessageBox.information(self, "API Key Test", summary)
        else:
            QMessageBox.warning(self, "API Key Test", summary)

    # -- mic logic ------------------------------------------------------------------
    def _refresh_mics(self) -> None:
        current = self._mic_combo.currentData() if hasattr(self, "_mic_combo") else None
        self._mic_combo.clear()
        self._mic_combo.addItem("Default Microphone", None)
        try:
            for index, name in list_input_devices():
                self._mic_combo.addItem(name, index)
        except Exception:
            pass
        if current is not None:
            for i in range(self._mic_combo.count()):
                if self._mic_combo.itemData(i) == current:
                    self._mic_combo.setCurrentIndex(i)
                    break

    def _toggle_mic_test(self) -> None:
        if self._mic_tester is not None and self._mic_tester.isRunning():
            self._stop_mic_test()
        else:
            self._mic_tester = _LiveMicTester(device_id=self._mic_combo.currentData())
            self._mic_tester.level_changed.connect(self._mic_level.setValue)
            self._mic_tester.finished.connect(self._on_mic_done)
            self._mic_tester.finished_test.connect(self._on_mic_done)
            self._mic_test_btn.setText("⏹ Stop Test")
            self._mic_tester.start()

    def _stop_mic_test(self) -> None:
        if self._mic_tester is not None:
            try:
                self._mic_tester.stop()
                self._mic_tester.wait(500)
            except Exception:
                pass
        self._on_mic_done()

    def _on_mic_done(self, *args) -> None:
        try:
            self._mic_test_btn.setText("🎤 Test Mic")
            self._mic_level.setValue(0)
        except Exception:
            pass
        self._mic_tester = None

    # -- accessors (no Settings writes) -----------------------------------------------
    def keys(self) -> list[str]:
        return self._collect_keys()

    def language(self) -> str:
        return str(self._lang_combo.currentData() or "auto")

    def hotkey(self) -> int:
        data = self._hotkey_combo.currentData()
        return int(data) if data is not None else 0x78

    def microphone_device_id(self) -> int | None:
        return self._mic_combo.currentData()

    # -- teardown -------------------------------------------------------------------------
    def _cleanup(self) -> None:
        if self._mic_tester is not None:
            tester = self._mic_tester
            for sig in ("finished", "finished_test"):
                try:
                    getattr(tester, sig).disconnect()
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
            self._queue.shutdown()
        except Exception:
            pass
        try:
            self._test_all_btn.setEnabled(True)
            self._test_all_btn.setText("Test All")
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._cleanup()
        super().closeEvent(event)

    def accept(self) -> None:
        self._cleanup()
        super().accept()

    def reject(self) -> None:
        self._cleanup()
        super().reject()
