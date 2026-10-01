# tests/test_setup_wizard.py
"""UX Phase D: SetupWizard tests (offscreen)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from voice_typing.ui.setup_wizard import SetupWizard


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _wait_until(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(0.01)
    try:
        return bool(predicate())
    except Exception:
        return False


def test_wizard_init_pages_and_defaults():
    wiz = SetupWizard()
    try:
        assert wiz.windowTitle() == "VoiceType Setup"
        assert wiz._stack.count() == 4
        assert wiz._stack.currentIndex() == 0
        assert "Step 1" in wiz._step_label.text()
        assert wiz.keys() == []
        assert wiz.language() == "auto"
        assert wiz.hotkey() == 0x78  # first HOTKEY_OPTIONS entry (F9)
        assert wiz.microphone_device_id() is None
    finally:
        wiz._queue.shutdown()


def test_wizard_add_keys_masked_and_deduped():
    wiz = SetupWizard()
    try:
        wiz._key_input.setText("wizard-key-1")
        wiz._add_key()
        wiz._key_input.setText("wizard-key-2")
        wiz._add_key()
        assert wiz.keys() == ["wizard-key-1", "wizard-key-2"]
        assert "wizard-key-1" not in wiz._keys_list.item(0).text()
        # Duplicate ignored.
        wiz._key_input.setText("wizard-key-1")
        wiz._add_key()
        assert wiz.keys() == ["wizard-key-1", "wizard-key-2"]
        # Remove selected.
        wiz._keys_list.setCurrentRow(0)
        wiz._remove_key()
        assert wiz.keys() == ["wizard-key-2"]
    finally:
        wiz._queue.shutdown()


def test_wizard_test_all_with_patched_fetch():
    wiz = SetupWizard()
    try:
        wiz._key_input.setText("wk-1")
        wiz._add_key()
        wiz._key_input.setText("wk-2")
        wiz._add_key()
        finished = []
        wiz._queue.test_all_finished.connect(lambda r: finished.append(list(r)))
        with patch("voice_typing.ui.worker_queue.fetch_live_models",
                   return_value=["models/x"]), \
             patch.object(QMessageBox, "information") as mock_info:
            wiz._test_all()
            assert _wait_until(lambda: finished)
        assert len(finished[0]) == 2
        assert wiz._keys_status.text() == "● Valid"
        mock_info.assert_called_once()
        assert wiz._test_all_btn.isEnabled()
    finally:
        wiz._queue.shutdown()


def test_wizard_test_all_empty_warns():
    wiz = SetupWizard()
    try:
        assert wiz.keys() == []
        with patch.object(QMessageBox, "warning") as mock_warn:
            wiz._test_all()
            mock_warn.assert_called_once()
    finally:
        wiz._queue.shutdown()


def test_wizard_navigation_and_summary():
    wiz = SetupWizard()
    try:
        wiz._go_next()
        assert wiz._stack.currentIndex() == 1
        assert "Step 2" in wiz._step_label.text()
        wiz._go_next()
        assert wiz._stack.currentIndex() == 2
        wiz._go_back()
        assert wiz._stack.currentIndex() == 1
        wiz._go_next()
        wiz._go_next()
        assert wiz._stack.currentIndex() == 3
        assert wiz._next_btn.text() == "Finish"
        assert "Keys:" in wiz._summary_label.text()
    finally:
        wiz._queue.shutdown()


def test_wizard_language_hotkey_mic_accessors():
    wiz = SetupWizard()
    try:
        wiz._stack.setCurrentIndex(1)
        wiz._lang_combo.setCurrentIndex(1)  # thai
        assert wiz.language() == "thai"
        for i in range(wiz._hotkey_combo.count()):
            if wiz._hotkey_combo.itemData(i) == 0x79:
                wiz._hotkey_combo.setCurrentIndex(i)
                break
        assert wiz.hotkey() == 0x79
        assert wiz._mic_combo.count() >= 1
        assert wiz._mic_combo.itemData(0) is None
    finally:
        wiz._queue.shutdown()


def test_wizard_never_touches_settings():
    """The wizard module performs no direct Settings writes."""
    import pathlib

    text = pathlib.Path("voice_typing/ui/setup_wizard.py").read_text(encoding="utf-8")
    assert "SettingsManager" not in text
    assert "set_api_keys" not in text
    assert ".save()" not in text


def test_wizard_close_cleans_up_queue():
    from PySide6.QtGui import QCloseEvent

    wiz = SetupWizard()
    finished = []
    wiz._queue.test_all_finished.connect(lambda r: finished.append(True))
    with patch("voice_typing.ui.worker_queue.fetch_live_models",
               return_value=["models/x"]), \
         patch.object(QMessageBox, "information"):
        wiz._key_input.setText("wk-1")
        wiz._add_key()
        wiz._test_all()
        assert _wait_until(lambda: finished)
    assert wiz._queue._thread.isRunning()
    wiz.closeEvent(QCloseEvent())
    assert not wiz._queue._thread.isRunning()
