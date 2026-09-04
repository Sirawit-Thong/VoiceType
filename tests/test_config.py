# tests/test_config.py
import json
import os
from pathlib import Path

import pytest

from voice_typing.config.settings import SettingsManager


@pytest.fixture(autouse=True)
def _disable_vault_backend(monkeypatch):
    """Force fallback mode so these plaintext tests ignore any live OS vault.

    On machines with a usable Windows Credential Manager backend,
    SettingsManager.load() would otherwise migrate the fixture keys into
    the real vault and blank the JSON copies these tests assert on. The
    kill-switch is honored by credential_store's probe/migrate; it is a
    no-op on vault-free CI where the backend is already unavailable.
    """
    monkeypatch.setenv("VOICETYPE_CREDSTORE_DISABLED", "1")
    from voice_typing.config import credential_store as _cs

    _cs.refresh_backend_cache()
    yield
    _cs.refresh_backend_cache()


def test_settings_load_creates_default(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mode"] == "push_to_talk"
    assert data["hotkey"] == 0x78
    assert data["fast_mode"] is True


def test_settings_set_and_get(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    mgr.set("api_key", "test-key-123")
    mgr.save()
    mgr2 = SettingsManager(config_path)
    mgr2.load()
    assert mgr2.get("api_key") == "test-key-123"


def test_settings_get_default(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get("nonexistent_key", "fallback") == "fallback"


def test_settings_load_corrupted_falls_back(tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get("mode") == "push_to_talk"
