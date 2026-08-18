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
