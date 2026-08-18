# voice_typing/windows/hotkey.py
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import threading
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NONE = 0x0000


class HotkeyManager:
    def __init__(self) -> None:
        self._hotkeys: dict[int, Callable[[int], None]] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._thread_id = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def register(self, vk_code: int, callback: Callable[[int], None]) -> None:
        self._hotkeys[vk_code] = callback

    def unregister(self, vk_code: int) -> None:
        self._hotkeys.pop(vk_code, None)
        if self._running:
            user32.UnregisterHotKey(None, vk_code)

    def _message_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        for vk in self._hotkeys:
            user32.RegisterHotKey(None, vk, MOD_NONE, vk)
        msg = wintypes.MSG()
        while self._running:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0 or result == -1:
                break
            if msg.message == WM_HOTKEY:
                vk = msg.wParam & 0xFFFFFFFF
                cb = self._hotkeys.get(vk)
                if cb is not None:
                    try:
                        cb(vk)
                    except Exception:
                        pass
        for vk in self._hotkeys:
            user32.UnregisterHotKey(None, vk)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None