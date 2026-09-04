# voice_typing/ui/history_dialog.py
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class HistoryDialog(QDialog):
    """Filterable dropdown + Pin / Copy / Clear. Clear keeps pinned items."""

    def __init__(self, history: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("History")
        self.history = list(history)
        self._pin_states: dict[int, bool] = {
            i: bool(h["pinned"]) for i, h in enumerate(history)
        }
        self._duplicate_unpinned_indices: list[int] = []
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search...")
        self._search.textChanged.connect(self._on_filter)
        self._list = QComboBox(self)
        self._list.setEditable(False)
        self._pin_btn = QPushButton("Pin", self)
        self._copy_btn = QPushButton("Copy", self)
        self._clear_btn = QPushButton("Clear", self)
        self._pin_btn.clicked.connect(self._on_pin)
        self._copy_btn.clicked.connect(self._on_copy)
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._pin_btn)
        btn_row.addWidget(self._copy_btn)
        btn_row.addWidget(self._clear_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search:", self))
        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addLayout(btn_row)
        self._apply_filter("")
        self.setStyleSheet(
            "QDialog { background-color: #202124; color: #e8eaed; }"
            "QComboBox { background-color: #303134; color: #e8eaed; }"
            "QLineEdit { background-color: #303134; color: #e8eaed; border-radius: 4px; }"
            "QPushButton { background-color: #303134; color: #e8eaed; border-radius: 6px; padding: 4px 12px; }"
        )

    def _apply_filter(self, query: str) -> None:
        q = (query or "").strip().lower()
        seen_text: set[str] = set()
        self._list.clear()
        self._combo_to_history_idx: list[int] = []
        self._duplicate_unpinned_indices = []
        for i, entry in enumerate(self.history):
            t = str(entry.get("text", ""))
            if q and q not in t.lower():
                continue
            pinned = bool(entry.get("pinned", False))
            if t in seen_text and not pinned:
                self._duplicate_unpinned_indices.append(i)
                continue
            seen_text.add(t)
            label = f"📌 {t}" if pinned else t
            self._list.addItem(label)
            self._combo_to_history_idx.append(i)
        self._search.setFocus()

    def _on_filter(self) -> None:
        self._apply_filter(self._search.text())

    def _selected_history_idx(self) -> int | None:
        row = self._list.currentIndex()
        if row < 0 or row >= len(self._combo_to_history_idx):
            return None
        return self._combo_to_history_idx[row]

    def _on_pin(self) -> None:
        idx = self._selected_history_idx()
        if idx is None:
            return
        self.history[idx]["pinned"] = not self.history[idx].get("pinned", False)
        self._apply_filter(self._search.text())

    def _on_copy(self) -> None:
        idx = self._selected_history_idx()
        if idx is None:
            return
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.history[idx].get("text", ""))

    def _on_clear(self) -> None:
        self.history = [e for e in self.history if e.get("pinned", False)]
        self._apply_filter(self._search.text())
