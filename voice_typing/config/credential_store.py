"""DPAPI-backed secure storage for per-provider API keys (Windows).

This is the ONLY module allowed to import ``keyring``. Everything else
(settings manager, settings UI, worker snapshot helpers) calls the
functions below so a missing or broken backend is contained here and
unit tests can substitute a fake without touching the OS vault.

Vault identity (stable, documented):
- keyring service name: ``VoiceType``
- account per provider: ``voicetype/{provider_id}/api_key`` where
  ``{provider_id}`` is the exact lowercase registry ID (``gemini_live``,
  ``openai_realtime``, ``groq``, ``deepgram``, ``openai_compatible``,
  ``freellm``, or any future ID). No display names, model names, or
  URLs appear in the account string.

Outcome contract: backend problems never raise out of this module.
``get_api_key`` returns ``""`` on any failure; ``set_api_key`` /
``delete_api_key`` return ``True``/``False``; details are exposed only
as short machine-readable status strings via ``last_backend_status()``
(``ok``, ``no_backend``, ``locked``, ``denied``, ``failed``). No key
material ever appears in statuses or logs.
"""
from __future__ import annotations

from typing import Any

SERVICE_NAME = "VoiceType"
PROBE_ACCOUNT = "voicetype/__probe__"

_OK = "ok"
_NO_BACKEND = "no_backend"
_LOCKED = "locked"
_DENIED = "denied"
_FAILED = "failed"

_backend_available: bool | None = None
_last_status: str = _NO_BACKEND


def _account_for(provider_id: str) -> str:
    return f"voicetype/{provider_id}/api_key"


def _classify_exception(exc: BaseException) -> str:
    name = type(exc).__name__
    if name in ("NoKeyringError", "InitError", "NoStoredPasswordError", "NoKeyringBackendError"):
        return _NO_BACKEND
    if name == "KeyringLocked" or "locked" in name.lower():
        return _LOCKED
    if name == "KeyringDenied" or "denied" in name.lower():
        return _DENIED
    msg = str(exc).lower()
    if "no backend" in msg or "no keyring" in msg:
        return _NO_BACKEND
    if "locked" in msg:
        return _LOCKED
    if "denied" in msg or "access is denied" in msg:
        return _DENIED
    return _FAILED


def refresh_backend_cache() -> None:
    """Clear the cached availability probe (tests and Retry actions)."""
    global _backend_available, _last_status
    _backend_available = None
    _last_status = _NO_BACKEND


def last_backend_status() -> str:
    """Return the last machine-readable backend status."""
    return _last_status


def is_secure_backend_available() -> bool:
    """Return True only when the vault backend imports and probes cleanly.

    The probe reads a non-secret canary entry. The result is cached per
    process; call ``refresh_backend_cache()`` before re-probing (Retry).
    """
    global _backend_available, _last_status
    if _backend_available is not None:
        return _backend_available
    try:
        import keyring
    except ImportError:
        _backend_available = False
        _last_status = _NO_BACKEND
        return False
    try:
        if keyring.get_keyring() is None:
            _backend_available = False
            _last_status = _NO_BACKEND
            return False
        keyring.get_password(SERVICE_NAME, PROBE_ACCOUNT)
    except Exception as exc:
        _backend_available = False
        _last_status = _classify_exception(exc)
        return False
    _backend_available = True
    _last_status = _OK
    return True


def get_api_key(provider_id: str) -> str:
    """Return the vault value for a provider, or ``""`` on any failure."""
    global _last_status
    if not isinstance(provider_id, str) or not provider_id:
        return ""
    if not is_secure_backend_available():
        return ""
    try:
        import keyring

        value = keyring.get_password(SERVICE_NAME, _account_for(provider_id))
    except Exception as exc:
        _last_status = _classify_exception(exc)
        return ""
    if not isinstance(value, str) or not value:
        return ""
    return value


def set_api_key(provider_id: str, api_key: str) -> bool:
    """Write a key; an empty value deletes the entry. Never raises."""
    global _last_status
    if not isinstance(provider_id, str) or not provider_id:
        return False
    if not isinstance(api_key, str):
        return False
    if api_key == "":
        return delete_api_key(provider_id)
    if not is_secure_backend_available():
        return False
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, _account_for(provider_id), api_key)
    except Exception as exc:
        _last_status = _classify_exception(exc)
        return False
    _last_status = _OK
    return True


def delete_api_key(provider_id: str) -> bool:
    """Remove one provider entry; a missing entry counts as success."""
    global _last_status
    if not isinstance(provider_id, str) or not provider_id:
        return False
    if not is_secure_backend_available():
        return False
    try:
        import keyring

        try:
            keyring.delete_password(SERVICE_NAME, _account_for(provider_id))
        except Exception as exc:
            if type(exc).__name__ in ("PasswordDeleteError", "NoStoredPasswordError") or (
                "no password" in str(exc).lower() or "not found" in str(exc).lower()
            ):
                _last_status = _OK
                return True
            _last_status = _classify_exception(exc)
            return False
    except Exception as exc:
        _last_status = _classify_exception(exc)
        return False
    _last_status = _OK
    return True


def posture_token() -> str:
    """Return the redacted diagnostics token for storage posture."""
    if is_secure_backend_available():
        return "credential_store=vault"
    return "credential_store=fallback(plaintext)"


def _json_key(settings_data: dict[str, Any], provider_id: str) -> str:
    try:
        profiles = settings_data.get("provider_profiles")
    except AttributeError:
        return ""
    if not isinstance(profiles, dict):
        return ""
    raw = profiles.get(provider_id)
    if not isinstance(raw, dict):
        return ""
    value = raw.get("api_key", "")
    return value if isinstance(value, str) else ""


def migrate_plaintext_keys(settings_data: dict[str, Any]) -> list[str]:
    """Move every non-empty plaintext key into the vault.

    Migrates each ``provider_profiles.<pid>.api_key`` plus the legacy
    top-level ``api_key`` (into the ``gemini_live`` vault entry). Each
    JSON copy is blanked to ``""`` only after that provider's vault
    write succeeds, so a half-finished migration never destroys a key.
    The legacy value is written first so explicit per-provider values
    win on conflict. Returns the migrated provider IDs. Does NOT save
    the file; the caller saves once afterwards. Idempotent.
    """
    if not isinstance(settings_data, dict):
        return []
    if not is_secure_backend_available():
        return []
    migrated: list[str] = []
    try:
        legacy = settings_data.get("api_key", "")
    except AttributeError:
        return []
    if not isinstance(legacy, str):
        legacy = ""
    if legacy:
        if set_api_key("gemini_live", legacy):
            settings_data["api_key"] = ""
            migrated.append("gemini_live")
    profiles = settings_data.get("provider_profiles")
    if not isinstance(profiles, dict):
        return migrated
    for pid, raw in profiles.items():
        if not isinstance(pid, str) or not pid:
            continue
        if not isinstance(raw, dict):
            continue
        value = raw.get("api_key", "")
        if not isinstance(value, str) or not value:
            continue
        if set_api_key(pid, value):
            raw["api_key"] = ""
            if pid not in migrated:
                migrated.append(pid)
    return migrated


def resolve_profile_key(settings_data: dict[str, Any], provider_id: str) -> str:
    """Single read path: vault value wins when available, else JSON.

    When the backend is available the vault value is returned if
    non-empty; otherwise the plaintext JSON value is used (covers keys
    that have not migrated yet due to a partial failure). When the
    backend is unavailable the JSON value is used (fallback mode).
    Empty vault plus empty JSON yields ``""``. Never raises.
    """
    if not isinstance(provider_id, str) or not provider_id:
        return ""
    if not isinstance(settings_data, dict):
        return ""
    try:
        fallback = _json_key(settings_data, provider_id)
    except Exception:
        fallback = ""
    try:
        if is_secure_backend_available():
            vault_value = get_api_key(provider_id)
            if vault_value:
                return vault_value
    except Exception:
        pass
    return fallback
