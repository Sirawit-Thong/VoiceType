# voice_typing/windows/hotkey.py
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import threading
import time
from collections.abc import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_UNREGISTER = 0x0400
WM_REGISTER = 0x0401
MOD_NONE = 0x0000
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

# Mouse Virtual Keys
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
MOUSE_VKS = {VK_MBUTTON, VK_XBUTTON1, VK_XBUTTON2}

HOTKEY_OPTIONS: list[tuple[str, int]] = [
    ("F9", 0x78),
    ("F10", 0x79),
    ("F8", 0x77),
    ("F7", 0x76),
    ("F6", 0x75),
    ("F11", 0x7A),
    ("F12", 0x7B),
    ("Mouse Side Button 1 (Back / X1)", 0x05),
    ("Mouse Side Button 2 (Forward / X2)", 0x06),
    ("Mouse Middle Click (Wheel)", 0x04),
    ("Scroll Lock", 0x91),
    ("Caps Lock", 0x14),
    ("Insert", 0x2D),
    ("Home", 0x24),
    ("End", 0x23),
]


# Known named keys dictionary
SPECIAL_KEY_NAMES: dict[int, str] = {
    0x01: "Mouse Left Click",
    0x02: "Mouse Right Click",
    0x04: "Mouse Middle Click (Wheel)",
    0x05: "Mouse Side Button 1 (Back / X1)",
    0x06: "Mouse Side Button 2 (Forward / X2)",
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x13: "Pause / Break",
    0x14: "Caps Lock",
    0x1B: "Escape",
    0x20: "Space",
    0x21: "Page Up",
    0x22: "Page Down",
    0x23: "End",
    0x24: "Home",
    0x25: "Left Arrow",
    0x26: "Up Arrow",
    0x27: "Right Arrow",
    0x28: "Down Arrow",
    0x2C: "Print Screen",
    0x2D: "Insert",
    0x2E: "Delete",
    0x5B: "Left Windows",
    0x5C: "Right Windows",
    0x5D: "Menu / Apps",
    0x60: "Numpad 0",
    0x61: "Numpad 1",
    0x62: "Numpad 2",
    0x63: "Numpad 3",
    0x64: "Numpad 4",
    0x65: "Numpad 5",
    0x66: "Numpad 6",
    0x67: "Numpad 7",
    0x68: "Numpad 8",
    0x69: "Numpad 9",
    0x6A: "Numpad *",
    0x6B: "Numpad +",
    0x6C: "Numpad Separator",
    0x6D: "Numpad -",
    0x6E: "Numpad .",
    0x6F: "Numpad /",
    0x90: "Num Lock",
    0x91: "Scroll Lock",
    0xBA: "; (Semicolon)",
    0xBB: "= (Equal)",
    0xBC: ", (Comma)",
    0xBD: "- (Minus)",
    0xBE: ". (Period)",
    0xBF: "/ (Slash)",
    0xC0: "` (Backtick / Tilde)",
    0xDB: "[ (Left Bracket)",
    0xDC: "\\ (Backslash)",
    0xDD: "] (Right Bracket)",
    0xDE: "' (Quote)",
}


def hotkey_name(vk_code: int) -> str:
    """Return a clean, human-readable name for any keyboard key or mouse button."""
    if vk_code in SPECIAL_KEY_NAMES:
        return SPECIAL_KEY_NAMES[vk_code]

    # Letters A-Z (0x41 to 0x5A)
    if 0x41 <= vk_code <= 0x5A:
        return f"Key {chr(vk_code)}"

    # Numbers 0-9 (0x30 to 0x39)
    if 0x30 <= vk_code <= 0x39:
        return f"Key {chr(vk_code)}"

    # Function keys F1-F24 (0x70 to 0x87)
    if 0x70 <= vk_code <= 0x87:
        return f"F{vk_code - 0x70 + 1}"

    # Query Windows OS API for key name
    try:
        scan_code = user32.MapVirtualKeyW(vk_code, 0)
        if scan_code:
            lParam = scan_code << 16
            buf = ctypes.create_unicode_buffer(64)
            if user32.GetKeyNameTextW(lParam, buf, 64) > 0:
                name = buf.value.strip()
                if name:
                    return name
    except Exception:
        pass

    return f"Key (VK {vk_code})"


class HotkeyManager:
    def __init__(self) -> None:
        self._hotkeys: dict[int, Callable[[int], None]] = {}
        self._release_callbacks: dict[int, Callable[[int], None]] = {}
        self._modifiers: dict[int, int] = {}
        self._registration_failures: list[int] = []
        self._active_release_waiters: set[int] = set()
        self._waiters_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._mouse_thread: threading.Thread | None = None
        self._running = False
        self._thread_id = 0
        self._started = threading.Event()
        self._mouse_pressed: dict[int, bool] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    def register(
        self,
        vk_code: int,
        callback: Callable[[int], None],
        on_release: Callable[[int], None] | None = None,
        modifiers: int = MOD_NONE,
    ) -> None:
        self._hotkeys[vk_code] = callback
        self._modifiers[vk_code] = modifiers
        if on_release is not None:
            self._release_callbacks[vk_code] = on_release
        else:
            self._release_callbacks.pop(vk_code, None)
        if self._running and self._started.is_set():
            user32.PostThreadMessageW(self._thread_id, WM_REGISTER, vk_code, 0)

    def unregister(self, vk_code: int) -> None:
        self._hotkeys.pop(vk_code, None)
        self._release_callbacks.pop(vk_code, None)
        self._modifiers.pop(vk_code, None)
        self._mouse_pressed.pop(vk_code, None)
        if self._running and self._started.is_set():
            user32.PostThreadMessageW(self._thread_id, WM_UNREGISTER, vk_code, 0)

    def _mouse_poll_loop(self) -> None:
        """Lightweight background poll for mouse button clicks (15ms sleep = ~60Hz, <0.01% CPU)."""
        while self._running:
            # Check registered mouse buttons
            for vk in list(self._hotkeys.keys()):
                if vk in MOUSE_VKS:
                    is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                    was_down = self._mouse_pressed.get(vk, False)
                    if is_down and not was_down:
                        self._mouse_pressed[vk] = True
                        cb = self._hotkeys.get(vk)
                        if cb is not None:
                            try:
                                cb(vk)
                            except Exception:
                                logging.warning(
                                    "Mouse hotkey callback failed VK=0x%X", vk, exc_info=True
                                )
                    elif not is_down and was_down:
                        self._mouse_pressed[vk] = False
                        release_cb = self._release_callbacks.get(vk)
                        if release_cb is not None:
                            try:
                                release_cb(vk)
                            except Exception:
                                logging.warning(
                                    "Mouse release callback failed VK=0x%X", vk, exc_info=True
                                )
            time.sleep(0.015)

    def _message_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._started.set()

        for vk in list(self._hotkeys.keys()):
            if vk not in MOUSE_VKS and user32.RegisterHotKey(None, vk, self._modifiers.get(vk, MOD_NONE), vk) == 0:
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
                        with self._waiters_lock:
                            if vk not in self._active_release_waiters:
                                self._active_release_waiters.add(vk)
                                threading.Thread(
                                    target=self._wait_for_release,
                                    args=(vk, release_cb),
                                    daemon=True,
                                    name="ReleaseWaiterThread",
                                ).start()
            elif msg.message == WM_REGISTER:
                vk = msg.wParam & 0xFFFFFFFF
                if vk not in MOUSE_VKS:
                    if user32.RegisterHotKey(None, vk, self._modifiers.get(vk, MOD_NONE), vk) == 0:
                        self._registration_failures.append(vk)
                        logging.warning("Failed to register hotkey VK=0x%X", vk)
                    else:
                        if vk in self._registration_failures:
                            self._registration_failures.remove(vk)
            elif msg.message == WM_UNREGISTER:
                vk = msg.wParam & 0xFFFFFFFF
                if vk not in MOUSE_VKS:
                    user32.UnregisterHotKey(None, vk)
                    if vk in self._registration_failures:
                        self._registration_failures.remove(vk)
        for vk in list(self._hotkeys.keys()):
            if vk not in MOUSE_VKS:
                user32.UnregisterHotKey(None, vk)

    def _wait_for_release(self, vk: int, on_release: Callable[[int], None]) -> None:
        try:
            deadline = time.monotonic() + 600.0
            while self._running and time.monotonic() < deadline:
                if not (user32.GetAsyncKeyState(vk) & 0x8000):
                    break
            if self._running:
                try:
                    on_release(vk)
                except Exception:
                    logging.warning(
                        "Hotkey release callback failed VK=0x%X", vk, exc_info=True
                    )
        finally:
            with self._waiters_lock:
                self._active_release_waiters.discard(vk)

    def start(self) -> None:
        if self._running:
            return
        self._registration_failures.clear()
        self._started.clear()
        self._mouse_pressed.clear()
        with self._waiters_lock:
            self._active_release_waiters.clear()
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True, name="HotkeyMsgLoopThread")
        self._thread.start()
        self._mouse_thread = threading.Thread(target=self._mouse_poll_loop, daemon=True, name="MousePollThread")
        self._mouse_thread.start()

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._started.wait(timeout=timeout)

    def registration_failures(self) -> list[int]:
        return list(self._registration_failures)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._started.wait(timeout=2.0):
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._mouse_thread is not None:
            self._mouse_thread.join(timeout=2.0)
            self._mouse_thread = None
        with self._waiters_lock:
            self._active_release_waiters.clear()

