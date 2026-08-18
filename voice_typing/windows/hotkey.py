# voice_typing/windows/hotkey.py
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
import time
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_UNREGISTER = 0x0400
MOD_NONE = 0x0000

HOTKEY_OPTIONS: list[tuple[str, int]] = [
    ("F6", 0x75),
    ("F7", 0x76),
    ("F8", 0x77),
    ("F9", 0x78),
    ("F10", 0x79),
    ("F11", 0x7A),
    ("F12", 0x7B),
    ("Scroll Lock", 0x91),
    ("Caps Lock", 0x14),
    ("Insert", 0x2D),
    ("Home", 0x24),
    ("End", 0x23),
]


def hotkey_name(vk_code: int) -> str:
    for name, code in HOTKEY_OPTIONS:
        if code == vk_code:
            return name
    return f"0x{vk_code:X}"


class HotkeyManager:
    def __init__(self) -> None:
        self._hotkeys: dict[int, Callable[[int], None]] = {}
        self._release_callbacks: dict[int, Callable[[int], None]] = {}
        self._registration_failures: list[int] = []
        self._thread: threading.Thread | None = None
        self._running = False
        self._thread_id = 0
        self._started = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    def register(
        self,
        vk_code: int,
        callback: Callable[[int], None],
        on_release: Callable[[int], None] | None = None,
    ) -> None:
        self._hotkeys[vk_code] = callback
        if on_release is not None:
            self._release_callbacks[vk_code] = on_release
        else:
            self._release_callbacks.pop(vk_code, None)

    def unregister(self, vk_code: int) -> None:
        self._hotkeys.pop(vk_code, None)
        self._release_callbacks.pop(vk_code, None)
        if self._running and self._started.wait(timeout=1.0):
            user32.PostThreadMessageW(self._thread_id, WM_UNREGISTER, vk_code, 0)

    def _message_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._started.set()
        for vk in self._hotkeys:
            if user32.RegisterHotKey(None, vk, MOD_NONE, vk) == 0:
                self._registration_failures.append(vk)
                logging.warning("Failed to register hotkey VK=0x%X", vk)
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
                        logging.warning(
                            "Hotkey callback failed VK=0x%X", vk, exc_info=True
                        )
                    release_cb = self._release_callbacks.get(vk)
                    if release_cb is not None:
                        threading.Thread(
                            target=self._wait_for_release,
                            args=(vk, release_cb),
                            daemon=True,
                        ).start()
            elif msg.message == WM_UNREGISTER:
                user32.UnregisterHotKey(None, msg.wParam & 0xFFFFFFFF)
        for vk in self._hotkeys:
            user32.UnregisterHotKey(None, vk)

    def _wait_for_release(self, vk: int, on_release: Callable[[int], None]) -> None:
        deadline = time.monotonic() + 600.0
        while self._running and time.monotonic() < deadline:
            if not (user32.GetAsyncKeyState(vk) & 0x8000):
                break
            time.sleep(0.03)
        try:
            on_release(vk)
        except Exception:
            logging.warning(
                "Hotkey release callback failed VK=0x%X", vk, exc_info=True
            )

    def start(self) -> None:
        if self._running:
            return
        self._registration_failures.clear()
        self._started.clear()
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._started.wait(timeout=2.0):
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
