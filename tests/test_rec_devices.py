import numpy as np

from knuzoom.recording.devices_windows import WindowsAudioSource, _to_stereo


def test_mono_block_is_duplicated_and_padded():
    out = _to_stereo(np.array([0.5, 0.25], np.float32), 4)
    assert out.shape == (4, 2) and out[0].tolist() == [0.5, 0.5] and out[3].tolist() == [0, 0]


def test_without_soundcard_returns_none_pair():
    # 이 개발 환경(Linux)에는 soundcard/장치가 없으므로 양쪽 None이어야 하고 예외가 없어야 한다
    src = WindowsAudioSource()
    assert src.read(960) == (None, None)
    src.close()
