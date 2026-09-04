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
