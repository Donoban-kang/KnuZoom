import numpy as np

from knuzoom.recording.overlay import RecordingOverlay


def test_overlay_marks_top_right_only():
    frame = np.zeros((720, 1280, 3), np.uint8)
    out = RecordingOverlay("B대학").apply(frame)
    assert out[16:60, 1280 - 300:1280 - 16].mean() > 0
    assert np.all(out[360:, :640] == 0)
    assert np.all(frame == 0)  # 원본은 그대로


def test_overlay_has_red_dot():
    out = RecordingOverlay("B대학").apply(np.zeros((720, 1280, 3), np.uint8))
    b, g, r = out[..., 0].astype(int), out[..., 1].astype(int), out[..., 2].astype(int)
    assert np.any((r > 150) & (g < 80) & (b < 80))


def test_overlay_on_tiny_frame_does_not_crash():
    out = RecordingOverlay("B대학").apply(np.zeros((40, 60, 3), np.uint8))
    assert out.shape == (40, 60, 3)
