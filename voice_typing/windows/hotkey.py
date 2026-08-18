from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import threading
from typing import Callable

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312
MOD_NONE = 0x0000


class HotkeyManager:
    def __init__(self) -> None:
        self._hotkeys: dict[int, Callable[[int], None]] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._hwnd: int | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def register(self, vk_code: int, callback: Callable[[int], None]) -> None:
        self._hotkeys[vk_code] = callback

    def unregister(self, vk_code: int) -> None:
        self._hotkeys.pop(vk_code, None)

    def _message_loop(self) -> None:
        msg = wintypes.MSG()
        while self._running:
            b = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if b == 0 or b == -1:
                break
            if msg.message == WM_HOTKEY:
                vk = msg.wParam & 0xFFFFFFFF
                cb = self._hotkeys.get(vk)
                if cb is not None:
                    cb(vk)

    def start(self) -> None:
        if self._running:
            return
        for vk in self._hotkeys:
            user32.RegisterHotKey(None, vk, MOD_NONE, vk)
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for vk in self._hotkeys:
            user32.UnregisterHotKey(None, vk)
        if self._hwnd is not None:
            user32.PostMessageW(self._hwnd, 0x0012, 0, 0)
