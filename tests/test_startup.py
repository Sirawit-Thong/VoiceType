# tests/test_startup.py
from unittest.mock import MagicMock, patch

from voice_typing.windows.startup import set_startup


def test_set_startup_enabled_writes_registry():
    fake_key = MagicMock()
    with patch("voice_typing.windows.startup.winreg.OpenKey", return_value=fake_key):
        assert set_startup(True) is True
    key = fake_key.__enter__.return_value
    key.SetValueEx.assert_called_once()
    assert key.SetValueEx.call_args.args[0] == "VoiceType"


def test_set_startup_disabled_deletes_value():
    fake_key = MagicMock()
    with patch("voice_typing.windows.startup.winreg.OpenKey", return_value=fake_key):
        assert set_startup(False) is True
    fake_key.__enter__.return_value.DeleteValue.assert_called_once()


def test_set_startup_handles_registry_error():
    with patch(
        "voice_typing.windows.startup.winreg.OpenKey",
        side_effect=OSError("access denied"),
    ):
        assert set_startup(True) is False