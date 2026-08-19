from __future__ import annotations

import ctypes
import time

import pyperclip

user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUTUNION),
    ]


INPUT_KEYBOARD = 1

NO_SPACE_BEFORE = ".,!?;:ฯๆ"


def auto_space(previous: str, current: str) -> str:
    if not previous or not current:
        return current
    if previous[-1].isspace() or current[0] in NO_SPACE_BEFORE:
        return previous + current
    return previous + " " + current


def _send_unicode_char(char: str) -> bool:
    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        inp = INPUT(
            INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, ord(char), flags, 0, None))
        )
        sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if sent != 1:
            return False
    return True


def _send_key_down(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)


def _send_key_up(vk: int) -> None:
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


class TextInjector:
    def inject(self, text: str) -> bool:
        if self._clipboard_inject(text):
            return True
        if self._sendinput_inject(text):
            return True
        return False

    def _clipboard_inject(self, text: str) -> bool:
        try:
            original = pyperclip.paste()
        except Exception:
            original = ""
        try:
            pyperclip.copy(text)
            time.sleep(0.02)
            _send_key_down(VK_CONTROL)
            _send_key_down(VK_V)
            time.sleep(0.01)
            _send_key_up(VK_V)
            _send_key_up(VK_CONTROL)
            time.sleep(0.02)
            return True
        except Exception:
            return False
        finally:
            try:
                if original:
                    pyperclip.copy(original)
            except Exception:
                pass

    def _sendinput_inject(self, text: str) -> bool:
        try:
            for char in text:
                if not self._send_char(char):
                    return False
            return True
        except Exception:
            return False

    def _send_char(self, char: str) -> bool:
        codes = _char_to_vk_sc(char)
        if codes is None:
            return _send_unicode_char(char)
        for vk, sc, hold in codes:
            _send_key_down(vk)
            time.sleep(0.001)
        for vk, sc, hold in reversed(codes):
            _send_key_up(vk)
            time.sleep(0.001)
        return True


def _char_to_vk_sc(char: str) -> list[tuple[int, int, bool]] | None:
    scanned = user32.VkKeyScanW(ord(char))
    if scanned == 0xFFFF:
        return None
    vk = scanned & 0xFF
    sc = user32.MapVirtualKeyW(vk, 0)
    shift = (scanned >> 8) & 0xFF
    result = []
    if shift & 0x01:
        result.append((0x10, 0, True))
    result.append((vk, sc, False))
    return result
