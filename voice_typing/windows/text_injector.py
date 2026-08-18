from __future__ import annotations

import ctypes
import time

import pyperclip

user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


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
            user32.keybd_event(0, ord(char), KEYEVENTF_UNICODE, 0)
            time.sleep(0.001)
            user32.keybd_event(
                0, ord(char), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0
            )
            time.sleep(0.001)
            return True
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
