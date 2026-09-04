# tests/test_startup.py
from unittest.mock import MagicMock, patch

from voice_typing.windows.startup import set_startup


def test_set_startup_enabled_writes_registry():
    fake_key = MagicMock()
    with (
        patch("voice_typing.windows.startup.winreg.OpenKey", return_value=fake_key),
        patch("voice_typing.windows.startup.winreg.SetValueEx") as set_value,
    ):
        assert set_startup(True) is True
    set_value.assert_called_once()
    assert set_value.call_args.args[1] == "VoiceType"


def test_set_startup_disabled_deletes_value():
    fake_key = MagicMock()
    with (
        patch("voice_typing.windows.startup.winreg.OpenKey", return_value=fake_key),
        patch("voice_typing.windows.startup.winreg.DeleteValue") as del_value,
    ):
        assert set_startup(False) is True
    del_value.assert_called_once()


def test_set_startup_disabled_ignores_missing_value():
    with (
        patch("voice_typing.windows.startup.winreg.OpenKey", return_value=MagicMock()),
        patch(
            "voice_typing.windows.startup.winreg.DeleteValue",
            side_effect=FileNotFoundError,
        ),
    ):
        assert set_startup(False) is True


def test_set_startup_handles_registry_error():
    with patch(
        "voice_typing.windows.startup.winreg.OpenKey",
        side_effect=OSError("access denied"),
    ):
        assert set_startup(True) is False
