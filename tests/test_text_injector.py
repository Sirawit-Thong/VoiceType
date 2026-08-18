from unittest.mock import patch

from voice_typing.windows.text_injector import TextInjector


def test_injector_initialization():
    injector = TextInjector()
    assert injector is not None


@patch("voice_typing.windows.text_injector.pyperclip")
@patch("voice_typing.windows.text_injector.user32")
def test_clipboard_preservation(mock_user32, mock_pyperclip):
    mock_pyperclip.paste.return_value = "original text"
    injector = TextInjector()
    result = injector._clipboard_inject("new text")
    assert result is True
    mock_pyperclip.copy.assert_any_call("new text")
    mock_pyperclip.copy.assert_any_call("original text")