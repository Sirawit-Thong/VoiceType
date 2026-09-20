# voice_typing/windows/startup.py
from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "VoiceType"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = Path(sys.argv[0]).resolve()
    return f'"{sys.executable}" "{script}"'


def set_startup(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
                log.info("Windows startup enabled")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    log.info("Windows startup disabled")
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.warning("Failed to set Windows startup registry")
        return False


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False