# tests/test_settings_migration.py
import json

from voice_typing.config.settings import SettingsManager


def test_legacy_keys_migrate_into_gemini_profile(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_key": "legacy-key", "model": "models/legacy-model"}), encoding="utf-8")
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("provider_id") == "gemini_live"
    profiles = mgr.get("provider_profiles")
    assert profiles["gemini_live"]["api_key"] == "legacy-key"
    assert profiles["gemini_live"]["model"] == "models/legacy-model"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["provider_profiles"]["gemini_live"]["api_key"] == "legacy-key"


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_key": "legacy-key", "model": "models/legacy-model"}), encoding="utf-8")
    mgr = SettingsManager(path)
    mgr.load()
    before = path.read_text(encoding="utf-8")
    mgr2 = SettingsManager(path)
    mgr2.load()
    assert mgr2.migrate_provider_profiles() is False
    assert path.read_text(encoding="utf-8") == before


def test_migration_preserves_unknown_profiles(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "api_key": "legacy-key",
        "provider_id": "groq",
        "provider_profiles": {"groq": {"api_key": "groq-key", "model": "whisper-large-v3-turbo"}, "mystery": {"x": 1}},
    }), encoding="utf-8")
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("provider_id") == "groq"
    assert mgr.get("provider_profiles")["groq"]["api_key"] == "groq-key"
    assert mgr.get("provider_profiles")["mystery"] == {"x": 1}
    assert mgr.get("provider_profiles")["gemini_live"]["api_key"] == "legacy-key"


def test_migration_skips_when_legacy_keys_empty(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("provider_id") == "gemini_live"
    assert mgr.get("provider_profiles", {}) == {}
    assert mgr.get("text_cleanup") == {"enabled": False, "provider_id": ""}


def test_malformed_profiles_do_not_lose_data(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"api_key": "k", "provider_profiles": ["not", "a", "dict"]}), encoding="utf-8")
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("provider_profiles")["gemini_live"]["api_key"] == "k"
