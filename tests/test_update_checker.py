# tests/test_update_checker.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tomllib
from pathlib import Path

from voice_typing.config.settings import SettingsManager


def test_version_matches_pyproject():
    from voice_typing.version import __version__
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == pyproject["project"]["version"] == "0.1.0"


def test_new_settings_defaults_opt_in_off(tmp_path):
    mgr = SettingsManager(tmp_path / "settings.json")
    mgr.load()
    assert mgr.get("preview_enabled") is False
    assert mgr.get("undo_hotkey_vk") == 0x5A
    assert mgr.get("update_check_enabled") is False
    assert mgr.get("update_last_check") == ""


def test_undo_hotkey_vk_clamped_on_load(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"undo_hotkey_vk": 9999}', encoding="utf-8")
    mgr = SettingsManager(p)
    mgr.load()
    assert mgr.get("undo_hotkey_vk") == 0x5A


def test_parse_tag_matrix():
    from voice_typing.update.checker import parse_tag
    assert parse_tag("v1.0.0") == (1, 0, 0)
    assert parse_tag("1.0") == (1, 0)
    assert parse_tag("bad") == (0,)


def test_is_newer_matrix():
    from voice_typing.update.checker import is_newer
    assert is_newer("0.1.0", "v0.2.0") is True
    assert is_newer("0.2.0", "v0.2.0") is False
    assert is_newer("1.0", "1.0.1") is True
    assert is_newer("0.1.0", "garbage") is False


async def _fake_get_ok(url):
    assert "api.github.com" in url
    return 200, {"tag_name": "v9.9.9", "html_url": "https://example.com/r"}


async def _fake_get_boom(url):
    raise OSError("offline")


def test_check_available_and_fail_open():
    import asyncio

    from voice_typing.update.checker import check_for_updates
    r = asyncio.run(check_for_updates("0.1.0", http_get=_fake_get_ok))
    assert r.available is True and r.latest_tag == "v9.9.9"
    r2 = asyncio.run(check_for_updates("0.1.0", http_get=_fake_get_boom))
    assert r2.available is False and r2.error
