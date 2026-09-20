# voice_typing/config/logging_setup.py
"""Centralised logging configuration for VoiceType.

* Writes to ``%APPDATA%/VoiceType/voicetype.log``
* Rotates at 1 MB, keeps 3 backups
* DEBUG to file, INFO to console (stderr)
* Imported once at startup; all modules then just use ``logging.getLogger(__name__)``
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_DIR = Path.home() / "AppData" / "Roaming" / "VoiceType"
_LOG_FILE = _LOG_DIR / "voicetype.log"
_MAX_BYTES = 1_000_000  # 1 MB
_BACKUP_COUNT = 3


def setup_logging() -> Path:
    """Configure root logger and return the log file path.

    Safe to call multiple times (idempotent).
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()  # root logger

    # Avoid adding duplicate handlers on repeated calls.
    if getattr(root, "_voicetype_configured", False):
        return _LOG_FILE
    root._voicetype_configured = True  # type: ignore[attr-defined]

    root.setLevel(logging.DEBUG)

    # --- File handler (DEBUG, rotating) ---
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    # --- Console handler (INFO, only if running in a console) ---
    if sys.stderr is not None and root.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.INFO)
        console.setFormatter(
            logging.Formatter("%(levelname)s | %(name)s | %(message)s")
        )
        root.addHandler(console)

    logging.info("Logging started → %s", _LOG_FILE)
    return _LOG_FILE
