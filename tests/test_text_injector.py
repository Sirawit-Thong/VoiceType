from unittest.mock import patch

from voice_typing.windows.text_injector import TextInjector, auto_space


def test_injector_initialization():
    injector = TextInjector()
    assert injector is not None


def test_auto_space_adds_space_between_utterances():
    assert auto_space("สวัสดี", "ทำอะไรอยู่") == "สวัสดี ทำอะไรอยู่"


def test_auto_space_no_space_after_whitespace():
    assert auto_space("สวัสดี ", "ทำอะไรอยู่") == "สวัสดี ทำอะไรอยู่"


def test_auto_space_no_space_before_punctuation():
    assert auto_space("สวัสดี", ".ต่อไป") == "สวัสดี.ต่อไป"
    assert auto_space("สวัสดี", "ฯลฯ") == "สวัสดีฯลฯ"


def test_auto_space_empty_inputs():
    assert auto_space("", "text") == "text"
    assert auto_space("prev", "") == ""
    assert auto_space("", "") == ""


@patch("voice_typing.windows.text_injector.pyperclip")
@patch("voice_typing.windows.text_injector.user32")
def test_clipboard_preservation(mock_user32, mock_pyperclip):
    mock_pyperclip.paste.return_value = "original text"
    injector = TextInjector()
    result = injector._clipboard_inject("new text")
    assert result is True
    mock_pyperclip.copy.assert_any_call("new text")
    mock_pyperclip.copy.assert_any_call("original text")