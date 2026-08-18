# voice_typing/config/settings.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS: dict[str, Any] = {
    "api_key": "",
    "mode": "push_to_talk",
    "hotkey": 0x7E,
    "language": "auto",
    "fast_mode": True,
    "microphone_device_id": None,
    "show_status_bar": True,
    "start_with_windows": False,
    "sound_feedback": True,
    "typing_speed": 0,
}


class SettingsManager:
    def __init__(self, config_path: Path | str) -> None:
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}

    def load(self) -> None:
        if self._path.exists():
            raw = self._path.read_text(encoding="utf-8")
            self._data = json.loads(raw)
        else:
            self._data = dict(DEFAULT_SETTINGS)
            self.save()

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