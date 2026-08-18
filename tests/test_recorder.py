from unittest.mock import MagicMock, patch

from voice_typing.audio.recorder import AudioRecorder


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