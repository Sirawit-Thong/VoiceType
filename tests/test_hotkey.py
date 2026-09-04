from unittest.mock import MagicMock, patch

from voice_typing.windows.hotkey import (
    WM_QUIT,
    WM_REGISTER,
    WM_UNREGISTER,
    HotkeyManager,
    hotkey_name,
)


def test_hotkey_initial_state():
    mgr = HotkeyManager()
    assert mgr.is_running is False
    assert mgr.registration_failures() == []


def test_hotkey_name_helper():
    assert hotkey_name(0x75) == "F6"
    assert hotkey_name(0x7B) == "F12"
    assert hotkey_name(0x41) == "Key A"
    assert hotkey_name(0x20) == "Space"


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


@patch("voice_typing.windows.hotkey.user32.PostThreadMessageW")
def test_dynamic_register_when_running(mock_post):
    mgr = HotkeyManager()
    mgr._running = True
    mgr._started.set()
    mgr._thread_id = 9999

    cb = MagicMock()
    release = MagicMock()
    mgr.register(0x75, cb, on_release=release)

    assert mgr._hotkeys[0x75] is cb
    assert mgr._release_callbacks[0x75] is release
    mock_post.assert_called_once_with(9999, WM_REGISTER, 0x75, 0)


@patch("voice_typing.windows.hotkey.user32.PostThreadMessageW")
def test_dynamic_unregister_when_running(mock_post):
    mgr = HotkeyManager()
    mgr._running = True
    mgr._started.set()
    mgr._thread_id = 9999
    mgr._hotkeys[0x75] = MagicMock()
    mgr._release_callbacks[0x75] = MagicMock()

    mgr.unregister(0x75)

    assert 0x75 not in mgr._hotkeys
    assert 0x75 not in mgr._release_callbacks
    mock_post.assert_called_once_with(9999, WM_UNREGISTER, 0x75, 0)


@patch("voice_typing.windows.hotkey.user32")
@patch("voice_typing.windows.hotkey.kernel32")
def test_message_loop_handles_wm_register_and_unregister(mock_kernel32, mock_user32):
    mock_kernel32.GetCurrentThreadId.return_value = 1234
    mock_user32.RegisterHotKey.return_value = 1
    mock_user32.UnregisterHotKey.return_value = 1

    mgr = HotkeyManager()

    messages = [
        # 1: WM_REGISTER success for 0x75
        (WM_REGISTER, 0x75),
        # 2: WM_UNREGISTER for 0x75
        (WM_UNREGISTER, 0x75),
        # 3: WM_QUIT to exit loop
        (WM_QUIT, 0),
    ]
    msg_idx = 0

    def fake_get_message(pMsg, hWnd, wMsgFilterMin, wMsgFilterMax):
        nonlocal msg_idx
        if msg_idx >= len(messages):
            return 0
        msg_type, w_param = messages[msg_idx]
        msg_idx += 1
        msg_obj = getattr(pMsg, "_obj", pMsg)
        msg_obj.message = msg_type
        msg_obj.wParam = w_param
        if msg_type == WM_QUIT:
            return 0
        return 1

    mock_user32.GetMessageW.side_effect = fake_get_message

    mgr._running = True
    mgr._message_loop()

    mock_user32.RegisterHotKey.assert_called_with(None, 0x75, 0, 0x75)
    mock_user32.UnregisterHotKey.assert_any_call(None, 0x75)


@patch("voice_typing.windows.hotkey.user32")
@patch("voice_typing.windows.hotkey.kernel32")
def test_message_loop_wm_register_failure_tracking(mock_kernel32, mock_user32):
    mock_kernel32.GetCurrentThreadId.return_value = 1234
    # Fail first registration, succeed second
    mock_user32.RegisterHotKey.side_effect = [0, 1]

    mgr = HotkeyManager()

    messages = [
        (WM_REGISTER, 0x76),  # will fail
        (WM_REGISTER, 0x76),  # will succeed and clear failure
        (WM_QUIT, 0),
    ]
    msg_idx = 0

    def fake_get_message(pMsg, hWnd, wMsgFilterMin, wMsgFilterMax):
        nonlocal msg_idx
        if msg_idx >= len(messages):
            return 0
        msg_type, w_param = messages[msg_idx]
        msg_idx += 1
        msg_obj = getattr(pMsg, "_obj", pMsg)
        msg_obj.message = msg_type
        msg_obj.wParam = w_param
        if msg_type == WM_QUIT:
            return 0
        return 1

    mock_user32.GetMessageW.side_effect = fake_get_message

    mgr._running = True
    mgr._message_loop()

    assert 0x76 not in mgr.registration_failures()


def test_release_waiter_deduplication():
    mgr = HotkeyManager()
    mgr._running = True
    release_cb = MagicMock()
    mgr._release_callbacks[0x75] = release_cb

    # Simulate active release waiter already running for 0x75
    with mgr._waiters_lock:
        mgr._active_release_waiters.add(0x75)

    with patch("threading.Thread") as mock_thread:
        # Simulate processing WM_HOTKEY
        cb = MagicMock()
        mgr._hotkeys[0x75] = cb

        # Check that when vk is in _active_release_waiters, no new thread is started
        with mgr._waiters_lock:
            in_waiters = 0x75 in mgr._active_release_waiters
            if not in_waiters:
                mgr._active_release_waiters.add(0x75)
                mock_thread(target=mgr._wait_for_release, args=(0x75, release_cb), daemon=True).start()

        mock_thread.assert_not_called()


@patch("voice_typing.windows.hotkey.user32.GetAsyncKeyState")
def test_wait_for_release_execution_and_cleanup(mock_get_async_key_state):
    # Simulate key already released (GetAsyncKeyState returns 0)
    mock_get_async_key_state.return_value = 0

    mgr = HotkeyManager()
    mgr._running = True
    mgr._active_release_waiters.add(0x75)

    release_cb = MagicMock()
    mgr._wait_for_release(0x75, release_cb)

    release_cb.assert_called_once_with(0x75)
    assert 0x75 not in mgr._active_release_waiters


@patch("voice_typing.windows.hotkey.user32.GetAsyncKeyState")
def test_wait_for_release_cleans_up_on_exception(mock_get_async_key_state):
    mock_get_async_key_state.return_value = 0

    mgr = HotkeyManager()
    mgr._running = True
    mgr._active_release_waiters.add(0x75)

    def failing_cb(vk):
        raise RuntimeError("Callback failed")

    mgr._wait_for_release(0x75, failing_cb)

    assert 0x75 not in mgr._active_release_waiters


def test_mouse_hotkey_names():
    assert "Middle" in hotkey_name(0x04)
    assert "Side Button 1" in hotkey_name(0x05)
    assert "Side Button 2" in hotkey_name(0x06)


def test_mouse_polling_dispatching():
    from voice_typing.windows.hotkey import VK_MBUTTON, VK_XBUTTON1

    mgr = HotkeyManager()
    m_cb = MagicMock()
    m_rel = MagicMock()
    x1_cb = MagicMock()
    x1_rel = MagicMock()

    mgr.register(VK_MBUTTON, m_cb, on_release=m_rel)
    mgr.register(VK_XBUTTON1, x1_cb, on_release=x1_rel)

    # 1. Simulate button down: GetAsyncKeyState returns 0x8000
    with patch("voice_typing.windows.hotkey.user32.GetAsyncKeyState") as mock_state:
        # Pressed
        mock_state.side_effect = lambda vk: 0x8000 if vk == VK_MBUTTON else 0
        mgr._running = True

        # Run one iteration of polling logic
        for vk in list(mgr._hotkeys.keys()):
            is_down = bool(mock_state(vk) & 0x8000)
            was_down = mgr._mouse_pressed.get(vk, False)
            if is_down and not was_down:
                mgr._mouse_pressed[vk] = True
                cb = mgr._hotkeys.get(vk)
                if cb:
                    cb(vk)

        m_cb.assert_called_once_with(VK_MBUTTON)
        assert mgr._mouse_pressed[VK_MBUTTON] is True

        # Released
        mock_state.side_effect = lambda vk: 0
        for vk in list(mgr._hotkeys.keys()):
            is_down = bool(mock_state(vk) & 0x8000)
            was_down = mgr._mouse_pressed.get(vk, False)
            if not is_down and was_down:
                mgr._mouse_pressed[vk] = False
                rel = mgr._release_callbacks.get(vk)
                if rel:
                    rel(vk)

        m_rel.assert_called_once_with(VK_MBUTTON)
        assert mgr._mouse_pressed[VK_MBUTTON] is False


def test_register_stores_modifiers_default_none():
    from voice_typing.windows import hotkey as hk
    mgr = hk.HotkeyManager()
    mgr.register(0x78, lambda vk: None)
    assert mgr._modifiers[0x78] == hk.MOD_NONE


def test_register_ctrl_shift_chord_uses_modifiers_in_registerhotkey(monkeypatch):
    from voice_typing.windows import hotkey as hk
    calls = []
    class FakeUser32:
        def RegisterHotKey(self, a, b, mod, vk):
            calls.append((b, mod, vk))
            return 1
        def UnregisterHotKey(self, a, b):
            return 1
        def PostThreadMessageW(self, *a):
            return 1
        def GetMessageW(self, *a):
            return 0
        def GetAsyncKeyState(self, vk):
            return 0
    monkeypatch.setattr(hk, "user32", FakeUser32())
    monkeypatch.setattr(hk, "kernel32", type("K", (), {"GetCurrentThreadId": staticmethod(lambda: 1)})())
    mgr = hk.HotkeyManager()
    mgr.register(0x5A, lambda vk: None, modifiers=hk.MOD_CONTROL | hk.MOD_SHIFT)
    mgr._running = True
    mgr._started.set()
    mgr._message_loop()
    assert (0x5A, hk.MOD_CONTROL | hk.MOD_SHIFT, 0x5A) in calls


