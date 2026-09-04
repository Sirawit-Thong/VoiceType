import json
import sys
from pathlib import Path
from typing import Any


def get_asset_path(filename: str = "icon.png") -> Path:
    """Resolve asset path reliably in normal python execution and PyInstaller bundled .exe."""
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "voice_typing" / "assets" / filename  # type: ignore[attr-defined]
        if p.exists():
            return p
        p2 = Path(sys._MEIPASS) / "assets" / filename  # type: ignore[attr-defined]
        if p2.exists():
            return p2
    pkg_assets = Path(__file__).resolve().parent.parent / "assets" / filename
    if pkg_assets.exists():
        return pkg_assets
    return pkg_assets


DEFAULT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "model": "models/gemini-3.1-flash-live-preview",
    "provider_id": "gemini_live",
    "provider_profiles": {},
    "text_cleanup": {"enabled": False, "provider_id": ""},
    "mode": "push_to_talk",
    "hotkey": 0x78,
    "language": "auto",
    "fast_mode": True,
    "microphone_device_id": None,
    "show_status_bar": True,
    "start_with_windows": False,
    "sound_feedback": True,
    "copy_to_clipboard": False,
    "typing_speed": 0,
    "capsule_style": "pill",
    "opacity": 0.94,
    "silence_threshold": 0.005,
    "custom_vocabulary": "",
    "preview_enabled": False,
    "undo_hotkey_vk": 0x5A,
    "update_check_enabled": False,
    "update_last_check": "",
}


class SettingsManager:
    def __init__(self, config_path: Path | str) -> None:
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}

    def load(self) -> None:
        if self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                loaded = json.loads(raw)
                self._data = {**DEFAULT_SETTINGS, **loaded}
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self._data = dict(DEFAULT_SETTINGS)
        else:
            self._data = dict(DEFAULT_SETTINGS)
            self.save()
            return
        self.migrate_provider_profiles()
        self.migrate_keys_to_vault()
        self._clamp_undo_hotkey_vk()

    def migrate_provider_profiles(self) -> bool:
        """Migrate legacy top-level api_key/model into the Gemini profile.

        Idempotent: a second call changes nothing and saves nothing.
        Unknown provider profiles are retained untouched. Saves only when
        a conversion actually changed the data.
        """
        data = self._data
        profiles = data.get("provider_profiles")
        if not isinstance(profiles, dict):
            profiles = {}
            data["provider_profiles"] = profiles
            changed = True
        else:
            changed = False
            if profiles is DEFAULT_SETTINGS.get("provider_profiles"):
                # Shallow-copy the shared default dict so later
                # profiles["gemini_live"] = ... does not mutate
                # DEFAULT_SETTINGS across SettingsManager instances/tests.
                profiles = dict(profiles)
                data["provider_profiles"] = profiles
        legacy_key = data.get("api_key", "")
        legacy_model = data.get("model", "")
        legacy_key = legacy_key if isinstance(legacy_key, str) else ""
        legacy_model = legacy_model if isinstance(legacy_model, str) else ""
        if legacy_model == DEFAULT_SETTINGS.get("model", ""):
            # Merged DEFAULT model is not user legacy data. An empty file {}
            # merges to the default model string; treating it as legacy would
            # create a gemini_live profile for fresh installs, breaking
            # test_migration_skips_when_legacy_keys_empty (expects {}).
            legacy_model = ""
        gemini = profiles.get("gemini_live")
        if not isinstance(gemini, dict):
            # Reconciled vs plan text: only create gemini_live when there is
            # legacy data to migrate. Unconditional creation would leave
            # {"gemini_live": {...}} for empty settings, breaking
            # test_migration_skips_when_legacy_keys_empty (expects {}) and
            # contradicting "saves only after successful conversion".
            if legacy_key or legacy_model:
                gemini = {}
                profiles["gemini_live"] = gemini
                changed = True
            else:
                gemini = None
        if gemini is not None and (legacy_key or legacy_model) and not gemini.get("api_key") and not gemini.get("model"):
            if legacy_key:
                gemini["api_key"] = legacy_key
            if legacy_model:
                gemini["model"] = legacy_model
            changed = True
        if not data.get("provider_id"):
            data["provider_id"] = "gemini_live"
            changed = True
        cleanup = data.get("text_cleanup")
        if not isinstance(cleanup, dict):
            data["text_cleanup"] = {"enabled": False, "provider_id": ""}
            changed = True
        if changed:
            self.save()
        return changed

    def migrate_keys_to_vault(self) -> list[str]:
        """Move plaintext API keys into the OS vault once, then save.

        Runs after migrate_provider_profiles() on every load. When no
        secure backend exists it does nothing (fallback mode keeps
        plaintext). When at least one key migrated, saves once. Never
        raises: vault errors must not break settings loading.
        """
        try:
            from voice_typing.config import credential_store as _cs
        except ImportError:
            return []
        try:
            if not _cs.is_secure_backend_available():
                return []
            migrated = _cs.migrate_plaintext_keys(self._data)
        except Exception:
            return []
        if migrated:
            try:
                self.save()
            except Exception:
                pass
        return migrated

    def _clamp_undo_hotkey_vk(self) -> None:
        vk = self._data.get("undo_hotkey_vk", 0x5A)
        valid = (
            isinstance(vk, int)
            and not isinstance(vk, bool)
            and ((0x41 <= vk <= 0x5A) or (0x30 <= vk <= 0x39))
        )
        if not valid:
            self._data["undo_hotkey_vk"] = 0x5A

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)
