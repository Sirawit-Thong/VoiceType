from unittest.mock import MagicMock, call, patch
import time

from voice_typing.windows.text_injector import (
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    TextInjector,
    _send_unicode_char,
    auto_space,
)


def test_injector_initialization():
    injector = TextInjector()
    assert injector.restore_delay == 0.2
    assert injector.typing_speed == 0.0

    custom = TextInjector(restore_delay=0.5, typing_speed=0.05)
    assert custom.restore_delay == 0.5
    assert custom.typing_speed == 0.05


def test_auto_space_adds_space_between_utterances():
    assert auto_space("สวัสดี", "ทำอะไรอยู่") == " ทำอะไรอยู่"


def test_auto_space_no_space_after_whitespace():
    assert auto_space("สวัสดี ", "ทำอะไรอยู่") == "ทำอะไรอยู่"


def test_auto_space_no_space_before_punctuation():
    assert auto_space("สวัสดี", ".ต่อไป") == ".ต่อไป"
    assert auto_space("สวัสดี", "ฯลฯ") == "ฯลฯ"


def test_auto_space_empty_inputs():
    assert auto_space("", "text") == "text"
    assert auto_space("prev", "") == ""
    assert auto_space("", "") == ""


@patch("voice_typing.windows.text_injector.pyperclip")
@patch("voice_typing.windows.text_injector.user32")
def test_clipboard_preservation_async(mock_user32, mock_pyperclip):
    mock_pyperclip.paste.return_value = "original text"
    injector = TextInjector(restore_delay=0.01)
    result = injector._clipboard_inject("new text")
    assert result is True
    mock_pyperclip.copy.assert_any_call("new text")

    # Allow async restore thread to run
    time.sleep(0.05)
    mock_pyperclip.copy.assert_any_call("original text")


@patch("voice_typing.windows.text_injector.pyperclip")
@patch("voice_typing.windows.text_injector.user32")
def test_clipboard_empty_original(mock_user32, mock_pyperclip):
    mock_pyperclip.paste.return_value = ""
    injector = TextInjector(restore_delay=0.01)
    result = injector._clipboard_inject("new text")
    assert result is True
    mock_pyperclip.copy.assert_called_once_with("new text")


@patch("voice_typing.windows.text_injector.pyperclip")
@patch("voice_typing.windows.text_injector.user32")
def test_clipboard_inject_failure_restores_original(mock_user32, mock_pyperclip):
    mock_pyperclip.paste.return_value = "original text"
    mock_user32.keybd_event.side_effect = RuntimeError("keybd_event failed")

    injector = TextInjector(restore_delay=0.2)
    result = injector._clipboard_inject("new text")
    assert result is False

    # Failure should trigger immediate async restore (delay=0.0)
    time.sleep(0.05)
    mock_pyperclip.copy.assert_any_call("original text")


@patch("voice_typing.windows.text_injector.user32.SendInput")
def test_send_unicode_char_bmp_thai_and_ascii(mock_send_input):
    mock_send_input.return_value = 1

    # Thai character 'ก' (0x0E01)
    assert _send_unicode_char("ก") is True
    assert mock_send_input.call_count == 2
    # Verify key down & key up flags
    first_input = mock_send_input.call_args_list[0][0][1]._obj
    assert first_input.union.ki.wScan == ord("ก")
    assert first_input.union.ki.dwFlags == KEYEVENTF_UNICODE

    second_input = mock_send_input.call_args_list[1][0][1]._obj
    assert second_input.union.ki.wScan == ord("ก")
    assert second_input.union.ki.dwFlags == (KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)


@patch("voice_typing.windows.text_injector.user32.SendInput")
def test_send_unicode_char_astral_plane_emoji(mock_send_input):
    mock_send_input.return_value = 1

    # Emoji '🚀' (U+1F680 -> UTF-16: 0xD83D, 0xDE80)
    assert _send_unicode_char("🚀") is True
    assert mock_send_input.call_count == 4


@patch("voice_typing.windows.text_injector._send_unicode_char")
def test_sendinput_inject_thai_text(mock_send_char):
    mock_send_char.return_value = True
    injector = TextInjector()
    text = "สวัสดีชาวโลก"
    assert injector._sendinput_inject(text) is True
    assert mock_send_char.call_count == len(text)
    mock_send_char.assert_has_calls([call(c) for c in text])


@patch("voice_typing.windows.text_injector.time.sleep")
@patch("voice_typing.windows.text_injector._send_unicode_char")
def test_sendinput_inject_typing_speed(mock_send_char, mock_sleep):
    mock_send_char.return_value = True
    injector = TextInjector(typing_speed=0.05)
    assert injector._sendinput_inject("ABC") is True
    assert mock_sleep.call_count == 3
    mock_sleep.assert_called_with(0.05)


def test_inject_fallback_logic():
    injector = TextInjector()

    with patch.object(injector, "_clipboard_inject", return_value=True), \
         patch.object(injector, "_sendinput_inject") as mock_sendinput:
        assert injector.inject("hello") is True
        mock_sendinput.assert_not_called()

    with patch.object(injector, "_clipboard_inject", return_value=False), \
         patch.object(injector, "_sendinput_inject", return_value=True) as mock_sendinput:
        assert injector.inject("hello") is True
        mock_sendinput.assert_called_once_with("hello", typing_speed=None)