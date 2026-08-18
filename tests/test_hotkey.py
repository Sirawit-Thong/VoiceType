from unittest.mock import MagicMock

from voice_typing.windows.hotkey import HotkeyManager


def test_hotkey_initial_state():
    mgr = HotkeyManager()
    assert mgr.is_running is False


def test_hotkey_register_unregister():
    mgr = HotkeyManager()
    cb = MagicMock()
    mgr.register(0x7E, cb)
    assert 0x7E in mgr._hotkeys
    mgr.unregister(0x7E)
    assert 0x7E not in mgr._hotkeys


def test_hotkey_register_with_release_callback():
    mgr = HotkeyManager()
    cb = MagicMock()
    release = MagicMock()
    mgr.register(0x78, cb, on_release=release)
    assert mgr._release_callbacks[0x78] is release
    mgr.register(0x78, cb)
    assert 0x78 not in mgr._release_callbacks
    mgr.unregister(0x78)
