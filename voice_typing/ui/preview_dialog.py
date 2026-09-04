# voice_typing/ui/preview_dialog.py
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout


class PreviewDialog(QDialog):
    """Opt-in preview: read-only text + Insert/Edit/Discard. Edit toggles editability."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm dictation")
        self.setModal(False)
        self._verdict: str | None = None  # "insert" | "discard" | None
        self._text = QTextEdit(self)
        self._text.setReadOnly(True)
        self._insert_btn = QPushButton("Insert", self)
        self._edit_btn = QPushButton("Edit", self)
        self._discard_btn = QPushButton("Discard", self)
        self._insert_btn.clicked.connect(self._on_insert)
        self._edit_btn.clicked.connect(self._on_edit)
        self._discard_btn.clicked.connect(self._on_discard)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._insert_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._discard_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self._text)
        layout.addLayout(btn_row)
        self.setStyleSheet(
            "QDialog { background-color: #202124; color: #e8eaed; }"
            "QTextEdit { background-color: #303134; color: #e8eaed; border: 1px solid #3c4043; border-radius: 6px; }"
            "QPushButton { background-color: #303134; color: #e8eaed; border-radius: 6px; padding: 6px 16px; }"
        )

    def set_text(self, text: str) -> None:
        """Last-wins: replace content, reset to read-only mode."""
        self._text.setPlainText(text)
        self._text.setReadOnly(True)
        self._verdict = None

    def current_text(self) -> str:
        return self._text.toPlainText()

    def take_verdict(self) -> str | None:
        v, self._verdict = self._verdict, None
        return v

    def _on_insert(self) -> None:
        self._verdict = "insert"
        self.accept()

    def _on_edit(self) -> None:
        self._text.setReadOnly(False)
        self._text.setFocus()

    def _on_discard(self) -> None:
        self._verdict = "discard"
        self.reject()
