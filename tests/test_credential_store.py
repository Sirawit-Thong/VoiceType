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


# --- migration + resolve tests appended in a later task ---
