from unittest.mock import MagicMock, patch

from voice_typing.audio.recorder import AudioRecorder, list_input_devices


def test_recorder_initial_state():
    rec = AudioRecorder()
    assert rec.is_recording is False


@patch("voice_typing.audio.recorder.sd")
def test_recorder_start_stop(mock_sd):
    rec = AudioRecorder()
    cb = MagicMock()
    rec.start(callback=cb)
    assert rec.is_recording is True
    mock_sd.InputStream.assert_called_once()
    rec.stop()
    assert rec.is_recording is False


@patch("voice_typing.audio.recorder.sd")
def test_recorder_start_with_device_id(mock_sd):
    rec = AudioRecorder()
    cb = MagicMock()
    rec.start(callback=cb, device_id=3)
    assert mock_sd.InputStream.call_args.kwargs["device"] == 3


@patch("voice_typing.audio.recorder.sd")
def test_list_input_devices_filters_inputs(mock_sd):
    mock_sd.query_devices.return_value = [
        {"name": "Speaker", "max_input_channels": 0},
        {"name": "Real Mic", "max_input_channels": 2},
        {"name": "Webcam Mic", "max_input_channels": 1},
    ]
    assert list_input_devices() == [(1, "Real Mic"), (2, "Webcam Mic")]
