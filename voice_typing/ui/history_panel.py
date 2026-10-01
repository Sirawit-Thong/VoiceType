# voice_typing/ui/history_panel.py
"""UX Phase D: read-only dictation history panel (embedded in Settings).

- Read-only list: full text in ``Qt.ItemDataRole.UserRole``, display is
  truncated with a tooltip; never editable.
- Buttons: Copy (clipboard + pyperclip fallback), Re-inject, Clear.
- :meth:`set_history` shows all given items newest-first (the app caps at
  20); the list scrolls.
- Signals: ``re_inject(text)`` and ``clear_history()`` — the app owns the
  actual history store and re-feeds the panel (round-trip).
- Never logs raw text (counts/lengths only).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QAbstractItemView,
)

log = logging.getLogger(__name__)

_DISPLAY_LIMIT = 80
_MAX_SHOWN = 20


def _display_text(full: str) -> str:
    flat = " ".join((full or "").split())
    if len(flat) > _DISPLAY_LIMIT:
        return flat[:_DISPLAY_LIMIT].rstrip() + "…"
    return flat


class HistoryPanel(QWidget):
    re_inject = Signal(str)
    clear_history = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._list = QListWidget()
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.clicked.connect(self._copy_selected)
        self._reinject_btn = QPushButton("Re-inject at cursor")
        self._reinject_btn.clicked.connect(self._emit_re_inject)
        self._clear_btn = QPushButton("Clear History")
        self._clear_btn.clicked.connect(self.clear_history.emit)
        btn_row.addWidget(self._copy_btn)
        btn_row.addWidget(self._reinject_btn)
        btn_row.addWidget(self._clear_btn)
        layout.addLayout(btn_row)

    # -- public ---------------------------------------------------------
    def count(self) -> int:
        return self._list.count()

    def set_history(self, items: list[str]) -> None:
        """Replace contents, newest-first. Shows all (up to 20), scrollable."""
        items = [str(t) for t in (items or [])]
        log.debug("HistoryPanel: showing %d item(s)", len(items))
        self._list.clear()
        for full in reversed(items[-_MAX_SHOWN:]):
            item = QListWidgetItem(_display_text(full))
            item.setData(Qt.ItemDataRole.UserRole, full)
            item.setToolTip(full)
            self._list.addItem(item)

    def selected_text(self) -> str:
        current = self._list.currentItem()
        if current is None:
            return ""
        full = current.data(Qt.ItemDataRole.UserRole)
        return full if isinstance(full, str) else ""

    # -- actions ----------------------------------------------------------
    def _copy_selected(self) -> None:
        text = self.selected_text()
        if not text:
            return
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(text)
                log.debug("HistoryPanel: copied (%d chars)", len(text))
                return
            raise RuntimeError("no clipboard")
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(text)
                log.debug("HistoryPanel: copied via pyperclip (%d chars)", len(text))
            except Exception:
                log.warning("HistoryPanel: copy to clipboard failed")

    def _emit_re_inject(self) -> None:
        text = self.selected_text()
        if text:
            log.debug("HistoryPanel: re-inject requested (%d chars)", len(text))
            self.re_inject.emit(text)
