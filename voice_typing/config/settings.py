import json
import sys
from pathlib import Path
from typing import Any

VERSION = "0.2.1"
RELEASE_URL = f"https://github.com/Sirawit-Thong/VoiceType/releases/tag/v{VERSION}"


def get_asset_path(filename: str = "icon.png") -> Path:
    """Resolve asset path reliably in normal python execution and PyInstaller bundled .exe."""
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "voice_typing" / "assets" / filename
        if p.exists():
            return p
        p2 = Path(sys._MEIPASS) / "assets" / filename
        if p2.exists():
            return p2
    pkg_assets = Path(__file__).resolve().parent.parent / "assets" / filename
    if pkg_assets.exists():
        return pkg_assets
    return pkg_assets


DEFAULT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "api_keys": [],
    "model": "models/gemini-3.1-flash-live-preview",
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
    # Transcript overlay settings
    "overlay_enabled": True,
    "overlay_opacity": 0.92,
    "overlay_font_size": 13,
    "overlay_max_height": 300,
    "overlay_auto_dismiss_seconds": 3,
    # UX Phase C: overlay geometry + pin (None = first-run default position)
    "overlay_x": None,
    "overlay_y": None,
    "overlay_width": 450,
    "overlay_height": 200,
    "overlay_pinned": False,
}

SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "Auto (Thai + English)"),
    ("thai", "Thai (ภาษาไทย)"),
    ("english", "English"),
]
LANGUAGE_INDEX = {code: i for i, (code, _) in enumerate(SUPPORTED_LANGUAGES)}


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
        self._sync_api_keys()
        self._validate_overlay_geometry()

    @staticmethod
    def _normalize_keys(keys: Any) -> list[str]:
        if not isinstance(keys, (list, tuple)):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            if not isinstance(k, str):
                continue
            s = k.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def _sync_api_keys(self) -> None:
        """Keep legacy ``api_key`` and ``api_keys`` consistent.

        - If ``api_keys`` is missing/empty and legacy ``api_key`` is non-empty
          → ``api_keys = [legacy]``.
        - If ``api_keys`` is non-empty → mirror ``api_key = api_keys[0]``.
        - Always store ``api_keys`` as a fresh normalized list (never share
          the ``DEFAULT_SETTINGS`` list object).
        """
        raw_keys = self._data.get("api_keys", [])
        keys = self._normalize_keys(raw_keys)
        legacy = self._data.get("api_key", "")
        legacy = legacy.strip() if isinstance(legacy, str) else ""
        if not keys and legacy:
            keys = [legacy]
        if keys:
            self._data["api_key"] = keys[0]
        self._data["api_keys"] = list(keys)

    def _validate_overlay_geometry(self) -> None:
        """Clamp Phase C overlay geometry/pin to sane ranges (in place)."""
        for key in ("overlay_x", "overlay_y"):
            val = self._data.get(key)
            if val is None:
                continue
            if isinstance(val, bool) or not isinstance(val, int):
                self._data[key] = None
            elif not -10000 <= val <= 10000:
                self._data[key] = None
        width = self._data.get("overlay_width")
        if isinstance(width, bool) or not isinstance(width, int):
            self._data["overlay_width"] = 450
        else:
            self._data["overlay_width"] = max(300, min(800, width))
        height = self._data.get("overlay_height")
        if isinstance(height, bool) or not isinstance(height, int):
            self._data["overlay_height"] = 200
        else:
            self._data["overlay_height"] = max(100, min(600, height))
        pinned = self._data.get("overlay_pinned")
        if not isinstance(pinned, bool):
            self._data["overlay_pinned"] = bool(pinned) if pinned in (0, 1) else False

    def get_api_keys(self) -> list[str]:
        keys = self._data.get("api_keys", [])
        normalized = self._normalize_keys(keys)
        # Legacy fallback if api_keys empty but api_key set (e.g. set directly).
        if not normalized:
            legacy = self._data.get("api_key", "")
            if isinstance(legacy, str) and legacy.strip():
                normalized = [legacy.strip()]
        return list(normalized)

    def set_api_keys(self, keys: list[str] | tuple[str, ...]) -> None:
        normalized = self._normalize_keys(keys)
        self._data["api_keys"] = list(normalized)
        if normalized:
            self._data["api_key"] = normalized[0]
        else:
            self._data["api_key"] = ""

    def save(self) -> None:
        import os
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, self._path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)