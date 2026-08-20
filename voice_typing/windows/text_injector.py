from __future__ import annotations

import ctypes
import threading
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
        return current
    return " " + current


def _send_unicode_char(char: str) -> bool:
    utf16_bytes = char.encode("utf-16le")
    utf16_units = [
        int.from_bytes(utf16_bytes[i : i + 2], "little")
        for i in range(0, len(utf16_bytes), 2)
    ]
    for unit in utf16_units:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(
                INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, unit, flags, 0, None))
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
    def __init__(
        self,
        restore_delay: float = 0.2,
        typing_speed: float = 0.0,
    ) -> None:
        self.restore_delay = restore_delay
        self.typing_speed = typing_speed

    def inject(self, text: str, typing_speed: float | None = None) -> bool:
        if self._clipboard_inject(text):
            return True
        if self._sendinput_inject(text, typing_speed=typing_speed):
            return True
        return False

    def _restore_clipboard_async(
        self, text: str, delay: float = 0.2
    ) -> threading.Thread:
        def _restore() -> None:
            if delay > 0:
                time.sleep(delay)
            try:
                pyperclip.copy(text)
            except Exception:
                pass

        t = threading.Thread(target=_restore, daemon=True)
        t.start()
        return t

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
            if original:
                self._restore_clipboard_async(original, delay=self.restore_delay)
            return True
        except Exception:
            if original:
                self._restore_clipboard_async(original, delay=0.0)
            return False

    def _sendinput_inject(
        self, text: str, typing_speed: float | None = None
    ) -> bool:
        speed = self.typing_speed if typing_speed is None else typing_speed
        try:
            for char in text:
                if not self._send_char(char):
                    return False
                if speed > 0:
                    time.sleep(speed)
            return True
        except Exception:
            return False

    def _send_char(self, char: str) -> bool:
        return _send_unicode_char(char)

