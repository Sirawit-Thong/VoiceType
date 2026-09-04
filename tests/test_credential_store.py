# tests/test_credential_store.py
"""Unit tests for voice_typing.config.credential_store.

No test contacts Windows Credential Manager, the network, or a live
provider. All secrets are synthetic placeholders. A dict-backed fake
`keyring` module is injected via sys.modules; the real OS vault is
never touched.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import types

import pytest

from voice_typing.config import credential_store as cs


class _FakeDeleteError(Exception):
    """Stands in for keyring.errors.PasswordDeleteError (missing entry)."""


def _install_fake_keyring(monkeypatch, store, fail_op=None, fail_probe=None):
    """Install a dict-backed fake `keyring` module into sys.modules.

    store: dict keyed by (service, account) holding secret strings.
    fail_op: exception raised by get/set/delete on real accounts.
    fail_probe: exception raised when reading the probe account.
    """
    fake = types.ModuleType("keyring")

    def get_keyring():
        return object()

    def get_password(service, account):
        if account == cs.PROBE_ACCOUNT and fail_probe is not None:
            raise fail_probe
        if account != cs.PROBE_ACCOUNT and fail_op is not None:
            raise fail_op
        return store.get((service, account))

    def set_password(service, account, value):
        if fail_op is not None:
            raise fail_op
        store[(service, account)] = value

    def delete_password(service, account):
        if fail_op is not None:
            raise fail_op
        try:
            del store[(service, account)]
        except KeyError:
            raise _FakeDeleteError(f"No password for {(service, account)}")

    fake.get_keyring = get_keyring
    fake.get_password = get_password
    fake.set_password = set_password
    fake.delete_password = delete_password
    monkeypatch.setitem(sys.modules, "keyring", fake)
    cs.refresh_backend_cache()
    return fake


@pytest.fixture(autouse=True)
def _fresh_cache():
    cs.refresh_backend_cache()
    yield
    cs.refresh_backend_cache()


def test_service_and_account_naming(monkeypatch):
    store = {}
    _install_fake_keyring(monkeypatch, store)
    assert cs.SERVICE_NAME == "VoiceType"
    assert cs.set_api_key("groq", "test-key-1") is True
    assert ("VoiceType", "voicetype/groq/api_key") in store
    assert store[("VoiceType", "voicetype/groq/api_key")] == "test-key-1"


def test_probe_success_sets_ok_status(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.is_secure_backend_available() is True
    assert cs.last_backend_status() == "ok"


def test_probe_caches_result(monkeypatch):
    store = {}
    _install_fake_keyring(monkeypatch, store)
    assert cs.is_secure_backend_available() is True
    # Break the backend after caching: cached True must survive.
    monkeypatch.delitem(sys.modules, "keyring")
    monkeypatch.setitem(sys.modules, "keyring", None)
    assert cs.is_secure_backend_available() is True
    cs.refresh_backend_cache()
    assert cs.is_secure_backend_available() is False
    assert cs.last_backend_status() == "no_backend"


def test_missing_keyring_means_no_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    assert cs.is_secure_backend_available() is False
    assert cs.last_backend_status() == "no_backend"
    assert cs.get_api_key("groq") == ""


def test_get_missing_returns_empty(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.get_api_key("groq") == ""


def test_set_then_get_round_trip(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.set_api_key("deepgram", "test-key-2") is True
    assert cs.get_api_key("deepgram") == "test-key-2"


def test_set_empty_deletes_entry(monkeypatch):
    store = {("VoiceType", "voicetype/groq/api_key"): "test-key-1"}
    _install_fake_keyring(monkeypatch, store)
    assert cs.set_api_key("groq", "") is True
    assert ("VoiceType", "voicetype/groq/api_key") not in store
    assert cs.get_api_key("groq") == ""


def test_delete_missing_returns_true(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.delete_api_key("groq") is True


def test_delete_existing_removes_entry(monkeypatch):
    store = {("VoiceType", "voicetype/groq/api_key"): "test-key-1"}
    _install_fake_keyring(monkeypatch, store)
    assert cs.delete_api_key("groq") is True
    assert ("VoiceType", "voicetype/groq/api_key") not in store


def test_empty_provider_id_rejected(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.set_api_key("", "test-key-1") is False
    assert cs.get_api_key("") == ""
    assert cs.delete_api_key("") is False


def test_backend_failure_never_raises(monkeypatch):
    _install_fake_keyring(monkeypatch, {}, fail_op=RuntimeError("vault boom"))
    assert cs.set_api_key("groq", "test-key-1") is False
    assert cs.get_api_key("groq") == ""
    assert cs.delete_api_key("groq") is False
    assert cs.last_backend_status() == "failed"


def test_locked_backend_maps_to_locked_status(monkeypatch):
    locked_cls = type("KeyringLocked", (Exception,), {})
    _install_fake_keyring(monkeypatch, {}, fail_op=locked_cls("vault locked"))
    assert cs.set_api_key("groq", "test-key-1") is False
    assert cs.last_backend_status() == "locked"


def test_status_strings_carry_no_key_material(monkeypatch):
    _install_fake_keyring(monkeypatch, {}, fail_op=RuntimeError("vault boom test-key-1"))
    cs.set_api_key("groq", "test-key-1")
    assert "test-key-1" not in cs.last_backend_status()


def test_migrate_moves_keys_and_blanks_json(monkeypatch):
    store = {}
    _install_fake_keyring(monkeypatch, store)
    data = {
        "api_key": "test-legacy-key",
        "provider_profiles": {
            "groq": {"api_key": "test-key-1", "model": "whisper-large-v3-turbo"},
            "deepgram": {"api_key": "test-key-2", "model": "nova-2"},
        },
    }
    migrated = cs.migrate_plaintext_keys(data)
    assert sorted(migrated) == ["deepgram", "gemini_live", "groq"]
    assert store[("VoiceType", "voicetype/groq/api_key")] == "test-key-1"
    assert store[("VoiceType", "voicetype/deepgram/api_key")] == "test-key-2"
    assert store[("VoiceType", "voicetype/gemini_live/api_key")] == "test-legacy-key"
    assert data["provider_profiles"]["groq"]["api_key"] == ""
    assert data["provider_profiles"]["deepgram"]["api_key"] == ""
    assert data["api_key"] == ""
    assert data["provider_profiles"]["groq"]["model"] == "whisper-large-v3-turbo"


def test_migrate_is_idempotent(monkeypatch):
    store = {}
    _install_fake_keyring(monkeypatch, store)
    data = {"api_key": "", "provider_profiles": {"groq": {"api_key": "test-key-1"}}}
    assert cs.migrate_plaintext_keys(data) == ["groq"]
    assert cs.migrate_plaintext_keys(data) == []
    assert store[("VoiceType", "voicetype/groq/api_key")] == "test-key-1"


def test_migrate_partial_failure_keeps_failed_key(monkeypatch):
    store = {}
    calls = []

    fake = _install_fake_keyring(monkeypatch, store)
    orig_set = fake.set_password

    def flaky_set(service, account, value):
        calls.append(account)
        if account == "voicetype/deepgram/api_key":
            raise RuntimeError("vault boom")
        return orig_set(service, account, value)

    fake.set_password = flaky_set
    data = {
        "api_key": "",
        "provider_profiles": {
            "groq": {"api_key": "test-key-1"},
            "deepgram": {"api_key": "test-key-2"},
        },
    }
    migrated = cs.migrate_plaintext_keys(data)
    assert migrated == ["groq"]
    assert data["provider_profiles"]["groq"]["api_key"] == ""
    assert data["provider_profiles"]["deepgram"]["api_key"] == "test-key-2"
    assert store.get(("VoiceType", "voicetype/groq/api_key")) == "test-key-1"
    assert ("VoiceType", "voicetype/deepgram/api_key") not in store


def test_migrate_no_backend_does_nothing(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    data = {"api_key": "test-legacy-key", "provider_profiles": {"groq": {"api_key": "test-key-1"}}}
    assert cs.migrate_plaintext_keys(data) == []
    assert data["provider_profiles"]["groq"]["api_key"] == "test-key-1"
    assert data["api_key"] == "test-legacy-key"


def test_resolve_vault_wins_over_json(monkeypatch):
    store = {("VoiceType", "voicetype/groq/api_key"): "test-vault-key"}
    _install_fake_keyring(monkeypatch, store)
    data = {"provider_profiles": {"groq": {"api_key": "test-json-key"}}}
    assert cs.resolve_profile_key(data, "groq") == "test-vault-key"


def test_resolve_falls_back_to_json_without_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    data = {"provider_profiles": {"groq": {"api_key": "test-json-key"}}}
    assert cs.resolve_profile_key(data, "groq") == "test-json-key"


def test_resolve_uses_json_when_vault_empty_but_available(monkeypatch):
    # Partial-failure shape: backend works, but this provider never migrated.
    _install_fake_keyring(monkeypatch, {})
    data = {"provider_profiles": {"groq": {"api_key": "test-json-key"}}}
    assert cs.resolve_profile_key(data, "groq") == "test-json-key"


def test_resolve_empty_vault_and_empty_json(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.resolve_profile_key({"provider_profiles": {"groq": {"api_key": ""}}}, "groq") == ""
    assert cs.resolve_profile_key({}, "groq") == ""
    assert cs.resolve_profile_key({"provider_profiles": {}}, "") == ""


def test_posture_token_values(monkeypatch):
    _install_fake_keyring(monkeypatch, {})
    assert cs.posture_token() == "credential_store=vault"
    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    assert cs.posture_token() == "credential_store=fallback(plaintext)"


def test_settings_load_migrates_keys_once_and_saves(monkeypatch, tmp_path):
    import json

    from voice_typing.config.settings import SettingsManager

    store = {}
    _install_fake_keyring(monkeypatch, store)
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"api_key": "test-legacy-key", "model": "models/legacy-model"}),
        encoding="utf-8",
    )
    mgr = SettingsManager(path)
    mgr.load()
    assert store.get(("VoiceType", "voicetype/gemini_live/api_key")) == "test-legacy-key"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["provider_profiles"]["gemini_live"]["api_key"] == ""
    assert saved["api_key"] == ""
    before = path.read_text(encoding="utf-8")
    mgr2 = SettingsManager(path)
    mgr2.load()
    assert path.read_text(encoding="utf-8") == before


def test_settings_load_fallback_keeps_plaintext(monkeypatch, tmp_path):
    import json

    from voice_typing.config.settings import SettingsManager

    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"provider_profiles": {"groq": {"api_key": "test-key-1"}}}),
        encoding="utf-8",
    )
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("provider_profiles")["groq"]["api_key"] == "test-key-1"
    assert cs.resolve_profile_key(mgr.as_dict(), "groq") == "test-key-1"


def test_settings_load_never_breaks_on_vault_error(monkeypatch, tmp_path):
    from voice_typing.config.settings import SettingsManager

    _install_fake_keyring(monkeypatch, {}, fail_probe=RuntimeError("vault boom"))
    path = tmp_path / "settings.json"
    mgr = SettingsManager(path)
    mgr.load()
    assert mgr.get("mode") == "push_to_talk"


def test_worker_snapshot_overlays_vault_key(monkeypatch, tmp_path):
    from voice_typing.config.settings import SettingsManager
    from voice_typing.providers.contracts import build_profile

    store = {("VoiceType", "voicetype/groq/api_key"): "test-vault-key"}
    _install_fake_keyring(monkeypatch, store)
    import voice_typing.app as app_module

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("provider_id", "groq")
    mgr.set("provider_profiles", {"groq": {"api_key": "", "model": "whisper-large-v3-turbo"}})
    worker = app_module.WorkerThread.__new__(app_module.WorkerThread)
    worker._settings = mgr
    profile = worker._snapshot_profile()
    assert profile.api_key == "test-vault-key"
    # The file-backed dict is never back-filled with the secret.
    assert mgr.get("provider_profiles")["groq"]["api_key"] == ""
    # build_profile itself is unchanged: raw dict in, same value out.
    assert build_profile({"provider_profiles": {"groq": {"api_key": "x"}}}, "groq").api_key == "x"


def test_worker_snapshot_falls_back_without_backend(monkeypatch, tmp_path):
    from voice_typing.config.settings import SettingsManager

    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    import voice_typing.app as app_module

    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    mgr.set("provider_id", "groq")
    mgr.set("provider_profiles", {"groq": {"api_key": "test-json-key"}})
    worker = app_module.WorkerThread.__new__(app_module.WorkerThread)
    worker._settings = mgr
    assert worker._snapshot_profile().api_key == "test-json-key"


def _make_dialog(tmp_path):
    from PySide6.QtWidgets import QApplication

    from voice_typing.config.settings import SettingsManager
    from voice_typing.ui.settings_window import SettingsWindow

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    win = SettingsWindow(mgr)
    return app, mgr, win


def test_dialog_populate_shows_vault_value(monkeypatch, tmp_path):
    store = {("VoiceType", "voicetype/groq/api_key"): "test-vault-key"}
    _install_fake_keyring(monkeypatch, store)
    _app, mgr, win = _make_dialog(tmp_path)
    mgr.set("provider_id", "groq")
    mgr.set("provider_profiles", {"groq": {"api_key": "", "model": "whisper-large-v3-turbo"}})
    win._populate_ui_from_settings()
    idx = win._provider_combo.findData("groq")
    win._provider_combo.setCurrentIndex(idx)
    assert win._api_key.text() == "test-vault-key"
    win.close()


def test_dialog_save_writes_vault_and_blanks_json(monkeypatch, tmp_path):
    import json

    store = {}
    _install_fake_keyring(monkeypatch, store)
    _app, mgr, win = _make_dialog(tmp_path)
    win._populate_ui_from_settings()
    idx = win._provider_combo.findData("groq")
    win._provider_combo.setCurrentIndex(idx)
    win._api_key.setText("test-key-9")
    win._store_current_profile_fields()
    win._save_and_close()
    assert store.get(("VoiceType", "voicetype/groq/api_key")) == "test-key-9"
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["provider_profiles"]["groq"]["api_key"] == ""
    win.close()


def test_dialog_fallback_banner_visible_without_backend(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "keyring", None)
    cs.refresh_backend_cache()
    _app, _mgr, win = _make_dialog(tmp_path)
    win._populate_ui_from_settings()
    assert not win._cred_banner.isHidden() or win._cred_banner.text() != ""
    assert "plaintext" in win._cred_banner.text()
    assert not win._cred_retry_btn.isHidden() or not win._cred_btn_widget.isHidden()
    win.close()


def test_dialog_no_banner_with_backend(monkeypatch, tmp_path):
    _install_fake_keyring(monkeypatch, {})
    _app, _mgr, win = _make_dialog(tmp_path)
    win._populate_ui_from_settings()
    assert win._cred_banner.text() == "" or not win._cred_banner.isVisible()
    win.close()


def test_dialog_reset_deletes_vault_entries(monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    store = {("VoiceType", "voicetype/groq/api_key"): "test-key-1"}
    _install_fake_keyring(monkeypatch, store)
    _app, mgr, win = _make_dialog(tmp_path)
    mgr.set("provider_profiles", {"groq": {"api_key": "", "model": "m"}})
    win._populate_ui_from_settings()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    win._reset_to_defaults()
    assert ("VoiceType", "voicetype/groq/api_key") not in store
    win.close()
