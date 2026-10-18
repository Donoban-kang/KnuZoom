import pytest

from fakes import FakeZoom
from knuzoom.config import Settings
from knuzoom.detector import FaceStats
from knuzoom.engine import Engine
from knuzoom.mic import MicController


def make_engine_with_log(z):
    log = []
    e = Engine(Settings(), MicController(z, 1.0, sleep=lambda _: None), log.append,
               clock_hms=lambda: "10:00:00")
    return e, log


def make_engine(z):
    return make_engine_with_log(z)[0]


def feed_stats(e, stats, t0, t1):
    t = t0
    while t <= t1 + 1e-9:
        e.on_stats(round(t, 6), stats)
        t += 0.2


def zoom_for(e, secs, t0):
    feed_stats(e, FaceStats(1, 0.3), t0, t0 + secs)


def wide_for(e, secs, t0):
    feed_stats(e, FaceStats(4, 0.08), t0, t0 + secs)


def test_start_mutes_on_first_tick():
    z = FakeZoom(muted=False); e = make_engine(z); e.tick()
    assert z.muted is True and e.status().muted is True


def test_zoom_unmutes_and_logs():
    z = FakeZoom(muted=True); e, log = make_engine_with_log(z)
    zoom_for(e, 1.2, t0=0.0)
    assert z.muted is False and log[-1] == "10:00:00 WIDE→ZOOM 해제 성공"


def test_pending_state_applied_when_meeting_appears():  # Review Focus 3
    z = FakeZoom(muted=False, active=False); e = make_engine(z)
    e.tick(); assert e.status().warning == "대기" and z.presses == 0
    z.active = True; e.tick()
    assert z.muted is True and e.status().warning is None


def test_auto_off_sends_nothing():
    z = FakeZoom(muted=True); e = make_engine(z); e.tick(); e.set_auto(False)
    zoom_for(e, 1.2, t0=0.0)
    assert z.presses == 0 and z.muted is True


def test_auto_on_applies_current_state():  # Review Focus 4
    z = FakeZoom(muted=True); e = make_engine(z); e.tick(); e.set_auto(False)
    zoom_for(e, 1.2, t0=0.0); e.set_auto(True)
    assert z.muted is False


def test_manual_change_respected_until_next_transition():
    z = FakeZoom(muted=True); e = make_engine(z)
    zoom_for(e, 1.2, t0=0.0); z.muted = True        # 진행자가 직접 음소거
    zoom_for(e, 1.0, t0=1.4); e.tick()
    assert z.muted is True                          # 다시 켜지 않음
    wide_for(e, 1.8, t0=2.6); zoom_for(e, 1.2, t0=4.6)
    assert z.muted is False                         # 다음 전환에서 재적용


def test_camera_lost_mutes_even_when_auto_off():
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    e.set_auto(False); e.on_camera_lost(2.0)
    assert z.muted is True and e.status().warning == "카메라 끊김"


def test_camera_recovery_clears_warning_and_requires_new_history():  # Review Focus 5
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    e.on_camera_lost(2.0)
    e.on_stats(3.0, FaceStats(1, 0.3))
    assert e.status().warning is None and z.muted is True


def test_host_block_warning():
    z = FakeZoom(muted=True, stuck=True); e = make_engine(z)
    zoom_for(e, 1.2, t0=0.0)
    assert e.status().warning == "호스트(A대학)가 해제를 막았을 수 있음"


def test_emergency_stop():
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    e.emergency_stop()
    assert z.muted is True and e.status().auto is False


def test_error_mutes():
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    e.on_error(RuntimeError("x"))
    assert z.muted is True and e.status().warning == "오류 발생"


def test_calibration_updates_thresholds():
    z = FakeZoom(); e = make_engine(z)
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(4, 0.10), 0.0, 2.2)
    e.start_calibration("zoom", 3.0); feed_stats(e, FaceStats(1, 0.30), 3.0, 5.2)
    assert e.s.wide_h == pytest.approx(0.16) and e.s.zoom_h == pytest.approx(0.24)


def test_calibration_failure_keeps_values():
    z = FakeZoom(); e = make_engine(z)
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(1, 0.30), 0.0, 2.2)
    e.start_calibration("zoom", 3.0); feed_stats(e, FaceStats(4, 0.10), 3.0, 5.2)
    assert (e.s.wide_h, e.s.zoom_h) == (0.15, 0.22)
    assert e.status().warning == "보정 실패: 확대 장면이 넓은 장면보다 커야 합니다"
