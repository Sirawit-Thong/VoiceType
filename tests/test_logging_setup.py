# tests/test_logging_setup.py
"""Tests for voice_typing.config.logging_setup."""

import logging
from pathlib import Path

from voice_typing.config.logging_setup import setup_logging


def test_setup_logging_creates_log_file(tmp_path, monkeypatch):
    """setup_logging should create a log file in the target directory."""
    import voice_typing.config.logging_setup as mod

    # Redirect log dir to a temp location
    monkeypatch.setattr(mod, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(mod, "_LOG_FILE", tmp_path / "voicetype.log")
    # Reset the configured flag so we can call it again
    root = logging.getLogger()
    if hasattr(root, "_voicetype_configured"):
        delattr(root, "_voicetype_configured")
    # Remove any existing handlers from previous calls
    handlers_before = list(root.handlers)

    log_file = setup_logging()
    assert log_file.exists()
    assert log_file.name == "voicetype.log"

    # Should be idempotent
    log_file2 = setup_logging()
    assert log_file2 == log_file

    # Cleanup: restore state
    root._voicetype_configured = False  # type: ignore
    for h in root.handlers[len(handlers_before):]:
        root.removeHandler(h)


def test_log_file_contains_entries(tmp_path, monkeypatch):
    """After setup_logging, writing to logger should appear in the file."""
    import voice_typing.config.logging_setup as mod

    monkeypatch.setattr(mod, "_LOG_DIR", tmp_path)
    monkeypatch.setattr(mod, "_LOG_FILE", tmp_path / "voicetype.log")
    root = logging.getLogger()
    if hasattr(root, "_voicetype_configured"):
        delattr(root, "_voicetype_configured")
    handlers_before = list(root.handlers)

    setup_logging()
    test_log = logging.getLogger("test_logging_setup")
    test_log.info("test message 12345")

    content = (tmp_path / "voicetype.log").read_text(encoding="utf-8")
    assert "test message 12345" in content
    assert "INFO" in content

    # Cleanup
    root._voicetype_configured = False  # type: ignore
    for h in root.handlers[len(handlers_before):]:
        root.removeHandler(h)
