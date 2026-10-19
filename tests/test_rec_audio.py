import numpy as np

from knuzoom.recording.audio_mix import BLOCK, MicGate, mix, to_s16le


def ones():
    return np.ones((960, 2), np.float32)


def test_block_is_20ms_stereo():
    assert BLOCK == 960


def test_gate_starts_closed():
    assert np.all(MicGate().process(ones(), False) == 0)


def test_gate_fades_in_over_20ms():
    out = MicGate().process(ones(), True)
    assert out[0, 0] < 0.01 and abs(out[-1, 0] - 1.0) < 0.01 and np.all(np.diff(out[:, 0]) >= 0)


def test_gate_fully_open_next_block():
    g = MicGate()
    g.process(ones(), True)
    assert np.allclose(g.process(ones(), True), 1.0)


def test_gate_fades_out():
    g = MicGate()
    g.process(ones(), True)
    out = g.process(ones(), False)
    assert out[0, 0] > 0.99 and out[-1, 0] < 0.01


def test_mix_clips():
    assert np.max(mix(ones(), ones())) == 1.0


def test_mix_none_is_silence():
    m = mix(None, None)
    assert m.shape == (960, 2) and np.all(m == 0)


def test_to_s16le():
    assert to_s16le(np.array([[1.0, -1.0]], np.float32)) == b"\xff\x7f\x01\x80"
