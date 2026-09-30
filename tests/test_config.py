# tests/test_config.py
import json
import os
from pathlib import Path

from voice_typing.config.settings import SettingsManager


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


def test_api_keys_default_empty(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get_api_keys() == []


def test_legacy_api_key_migrates_to_api_keys(tmp_path):
    import json as _json

    config_path = tmp_path / "settings.json"
    config_path.write_text(
        _json.dumps({"api_key": "test-key-legacy"}), encoding="utf-8"
    )
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get_api_keys() == ["test-key-legacy"]


def test_api_keys_mirrors_legacy_api_key(tmp_path):
    import json as _json

    config_path = tmp_path / "settings.json"
    config_path.write_text(
        _json.dumps({"api_keys": ["test-key-1", "test-key-2"]}), encoding="utf-8"
    )
    mgr = SettingsManager(config_path)
    mgr.load()
    assert mgr.get("api_key") == "test-key-1"
    assert mgr.get_api_keys() == ["test-key-1", "test-key-2"]


def test_set_api_keys_normalizes_and_mirrors(tmp_path):
    config_path = tmp_path / "settings.json"
    mgr = SettingsManager(config_path)
    mgr.load()
    mgr.set_api_keys(["  test-key-1 ", "", "test-key-1", "test-key-2"])
    assert mgr.get_api_keys() == ["test-key-1", "test-key-2"]
    assert mgr.get("api_key") == "test-key-1"
    mgr.save()
    mgr2 = SettingsManager(config_path)
    mgr2.load()
    assert mgr2.get_api_keys() == ["test-key-1", "test-key-2"]
    assert mgr2.get("api_key") == "test-key-1"
