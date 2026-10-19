from types import SimpleNamespace

import numpy as np

from knuzoom.config import Settings
from knuzoom.detector import FaceStats
from knuzoom.video_io import CameraPipeline

FRAME = np.zeros((720, 1280, 3), np.uint8)


class FakeCapture:
    def __init__(self, frames):
        self.frames = list(frames)
        self.released = False

    def read(self):
        if not self.frames:
            return False, None
        f = self.frames.pop(0)
        return (f is not None), f

    def release(self):
        self.released = True


class FakeVCam:
    def __init__(self):
        self.sent = 0

    def send(self, frame_rgb):
        self.sent += 1

    def sleep_until_next_frame(self):
        pass

    def close(self):
        pass


class FakeClock:
    def __init__(self):
        self.t = -1 / 30

    def __call__(self):
        return self.t


def raise_runtime_error(frame):
    raise RuntimeError("boom")


def make_pipeline(frames, analyze=None):
    h = SimpleNamespace(stats=[], lost=[], errors=[], vcam=FakeVCam(), clock=FakeClock())
    cap = FakeCapture(frames)
    p = CameraPipeline(
        Settings(),
        open_capture=lambda: cap,
        open_vcam=lambda: h.vcam,
        analyze=analyze or (lambda f: FaceStats(1, 0.3)),
        on_stats=lambda t, s: h.stats.append((t, s)),
        on_lost=h.lost.append,
        on_error=h.errors.append,
        clock=h.clock,
    )
    orig_step = p.step

    def step():
        h.clock.t += 1 / 30
        orig_step()

    h.p = SimpleNamespace(step=step)
    return h


def test_every_frame_forwarded_analysis_at_5fps():
    h = make_pipeline(frames=[FRAME] * 30)
    for _ in range(30): h.p.step()
    assert h.vcam.sent == 30 and len(h.stats) == 5   # t=0, .2, .4, .6, .8


def test_camera_lost_after_15_failures_called_once():
    h = make_pipeline(frames=[None] * 40)
    for _ in range(40): h.p.step()
    assert len(h.lost) == 1 and h.vcam.sent == 0


def test_analyze_exception_goes_to_on_error_and_continues():
    h = make_pipeline(frames=[FRAME] * 10, analyze=raise_runtime_error)
    for _ in range(10): h.p.step()
    assert len(h.errors) >= 1 and h.vcam.sent == 10


def test_reconnects_after_two_seconds_and_resumes_stats():
    h = make_pipeline(frames=[None] * 15 + [FRAME] * 30)
    for _ in range(15): h.p.step()
    assert len(h.lost) == 1 and h.stats == []
    for _ in range(59): h.p.step()          # 재연결 대기(2초 미만)
    assert h.stats == []
    for _ in range(10): h.p.step()
    assert len(h.lost) == 1 and len(h.stats) >= 1


def test_run_survives_read_exception_and_reports_it():  # Final C3
    import threading

    class BoomCapture(FakeCapture):
        def read(self):
            raise OSError("device gone")

    h = SimpleNamespace(errors=[])
    stop = threading.Event()
    p = CameraPipeline(Settings(), open_capture=lambda: BoomCapture([]), open_vcam=FakeVCam,
                       analyze=lambda f: FaceStats(1, 0.3), on_stats=lambda t, s: None,
                       on_lost=lambda t: None,
                       on_error=lambda e: (h.errors.append(e), stop.set()))
    p.run(stop)
    assert isinstance(h.errors[0], OSError)


def test_frame_resized_to_vcam_size():  # Final I5
    got = []

    class SizedVCam(FakeVCam):
        def send(self, frame_rgb):
            got.append(frame_rgb.shape)

    p = CameraPipeline(Settings(), open_capture=lambda: FakeCapture([np.zeros((480, 640, 3), np.uint8)]),
                       open_vcam=SizedVCam, analyze=lambda f: FaceStats(1, 0.3),
                       on_stats=lambda t, s: None, on_lost=lambda t: None, on_error=got.append)
    p.step()
    assert got == [(720, 1280, 3)]


def test_open_failure_reported_as_lost_once():  # M6
    lost, clock = [], FakeClock()

    def boom():
        raise OSError("no device")

    p = CameraPipeline(Settings(), open_capture=boom, open_vcam=FakeVCam,
                       analyze=lambda f: FaceStats(1, 0.3), on_stats=lambda t, s: None,
                       on_lost=lost.append, on_error=lambda e: None, clock=clock)
    for _ in range(200):
        clock.t += 1 / 30
        p.step()
    assert len(lost) == 1


def test_open_real_capture_raises_when_device_missing():  # 재검토 M6
    import pytest
    from knuzoom.video_io import open_real_capture
    with pytest.raises(OSError):
        open_real_capture(Settings(camera_index=99))
