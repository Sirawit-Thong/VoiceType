from __future__ import annotations

import ctypes
import time

import pyperclip

user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002


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
                for vk, sc in _char_to_vk_sc(char):
                    _send_key_down(vk)
                    time.sleep(0.001)
                    _send_key_up(vk)
                    time.sleep(0.001)
            return True
        except Exception:
            return False


def _char_to_vk_sc(char: str) -> list[tuple[int, int]]:
    vk = user32.VkKeyScanW(ord(char)) & 0xFF
    sc = user32.MapVirtualKeyW(vk, 0)
    shift = (user32.VkKeyScanW(ord(char)) >> 8) & 0xFF
    result = []
    if shift & 0x01:
        result.append((0x10, 0))
    result.append((vk, sc))
    return result
