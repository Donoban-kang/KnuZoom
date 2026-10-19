import pytest

from fakes import FakeZoom
from knuzoom.config import Settings
from knuzoom.detector import FaceStats
from knuzoom.engine import Engine
from knuzoom.mic import MicController


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_engine_with_log(z, run=None, clock=None):
    log = []
    kw = {} if run is None else {"run": run}
    e = Engine(Settings(), MicController(z, 1.0, sleep=lambda _: None), log.append,
               clock_hms=lambda: "10:00:00", clock=clock or Clock(), **kw)
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
    z.active = True; e.clock.t += 1.0; e.tick()
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


def test_audio_joined_unmuted_after_unreadable_start_gets_muted():  # Final C2
    z = FakeZoom(muted=False, readable=False); e = make_engine(z)
    e.tick()                                   # 오디오 미연결: 상태 읽기 불가 → 추정
    z.readable = True                          # 컴퓨터 오디오 연결(해제 상태로 들어옴)
    e.clock.t += 1.0; e.tick()
    assert z.muted is True


def test_rejoined_meeting_is_muted_again():  # Final C2
    z = FakeZoom(muted=True); e = make_engine(z); e.tick()
    z.active = False; e.clock.t += 2.0; e.tick()      # 회의 퇴장 감지
    z.active = True; z.muted = False                  # 새 회의에 해제 상태로 입장
    e.clock.t += 2.0; e.tick(); e.clock.t += 1.0; e.tick()
    assert z.muted is True


def test_watchdog_mutes_when_stats_stop():  # Final C3
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    assert z.muted is False
    e.clock.t += 2.5; e.tick()
    assert z.muted is True and e.status().warning == "카메라 끊김"


def test_failed_mute_is_retried_and_unconfirmed():  # Final I4
    z = FakeZoom(muted=True); e = make_engine(z); zoom_for(e, 1.2, t0=0.0)
    z.stuck = True
    wide_for(e, 1.8, t0=1.4)
    assert e.status().warning == "음소거 실패" and e.status().confirmed is False
    z.stuck = False; e.clock.t += 1.0; e.tick()
    assert z.muted is True and e.status().confirmed is True


def test_repeated_errors_do_not_pile_up_jobs():  # Final I5
    jobs = []
    z = FakeZoom(muted=True); e, _ = make_engine_with_log(z, run=jobs.append)
    for _ in range(100):
        e.on_error(RuntimeError("send failed"))
    e.emergency_stop()
    assert len(jobs) == 1
    jobs.pop()()
    assert z.muted is True


def test_sync_reconciles_toward_desired_mute():  # Final I6
    z = FakeZoom(muted=False, readable=False); e = make_engine(z)
    e.sync_mic(False)
    assert z.muted is True


def test_shutdown_mutes_synchronously():  # Final I7
    jobs = []
    z = FakeZoom(muted=True); e, _ = make_engine_with_log(z, run=jobs.append)
    zoom_for(e, 1.2, t0=0.0); jobs.clear(); z.muted = False
    e.shutdown()
    assert z.muted is True


def test_error_is_logged():  # Final I8
    z = FakeZoom(muted=True); e, log = make_engine_with_log(z)
    e.on_error(ValueError("frame shape"))
    assert any("오류" in line and "ValueError" in line and "frame shape" in line for line in log)


def test_auto_on_after_emergency_keeps_muted_until_new_zoom():
    z = FakeZoom(muted=True); e = make_engine(z)
    zoom_for(e, 1.2, t0=0.0)                        # 발언자 확대 → 해제
    e.emergency_stop(); e.set_auto(True)
    assert z.muted is True and e.status().muted is True
    assert e.status().warning == "긴급 정지 후 대기: 넓은 장면을 거쳐 다시 확대되면 자동 해제"
    zoom_for(e, 1.0, t0=1.4)                        # 같은 발언자 계속 확대 중
    assert z.muted is True
    wide_for(e, 1.8, t0=2.6)                        # 넓은 장면으로 복귀
    assert e.status().warning is None
    zoom_for(e, 1.2, t0=4.6)                        # 새 확대
    assert z.muted is False


def test_emergency_while_wide_does_not_hold_next_zoom():
    z = FakeZoom(muted=True); e = make_engine(z)
    wide_for(e, 1.0, t0=0.0)
    e.emergency_stop(); e.set_auto(True)
    assert e.status().warning is None
    zoom_for(e, 1.2, t0=1.2)
    assert z.muted is False


def test_calibration_without_faces_warns():  # M5
    z = FakeZoom(); e = make_engine(z)
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(0, 0.0), 0.0, 2.2)
    assert e.status().warning == "보정 실패: 얼굴이 검출되지 않았습니다"


def test_calibration_tiny_gap_warns():  # M5
    z = FakeZoom(); e = make_engine(z)
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(1, 0.20), 0.0, 2.2)
    e.start_calibration("zoom", 3.0); feed_stats(e, FaceStats(1, 0.22), 3.0, 5.2)
    assert (e.s.wide_h, e.s.zoom_h) == (0.15, 0.22)
    assert e.status().warning == "보정 실패: 넓은 장면과 확대 장면의 차이가 너무 작습니다"


def test_real_worker_thread_applies_latest_state_in_order():  # M8
    import time
    from concurrent.futures import ThreadPoolExecutor

    class SlowZoom(FakeZoom):
        def press_toggle(self):
            time.sleep(0.01)
            super().press_toggle()

    pool = ThreadPoolExecutor(max_workers=1)
    z = SlowZoom(muted=True); log = []
    e = Engine(Settings(), MicController(z, 0.0, sleep=lambda _: None), log.append,
               clock_hms=lambda: "10:00:00", run=pool.submit, clock=Clock())
    zoom_for(e, 1.2, t0=0.0)          # 해제 요청
    e.emergency_stop()                # 곧바로 음소거 요청
    pool.shutdown(wait=True)
    assert z.muted is True and e.status().muted is True
    assert log[-1].endswith("음소거 성공")


def test_mute_failure_warning_overrides_calibration_warning():  # 재검토 I1
    z = FakeZoom(muted=True); e = make_engine(z)
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(0, 0.0), 0.0, 2.2)
    assert e.status().warning == "보정 실패: 얼굴이 검출되지 않았습니다"
    zoom_for(e, 1.2, t0=3.0); z.stuck = True
    wide_for(e, 1.8, t0=4.4)
    assert e.status().warning == "음소거 실패"


def test_calibration_warning_does_not_hide_error():  # 재검토 I1
    z = FakeZoom(muted=True); e = make_engine(z)
    e.on_error(RuntimeError("x"))
    e.start_calibration("wide", 0.0); feed_stats(e, FaceStats(0, 0.0), 0.0, 2.2)
    assert e.status().warning == "오류 발생"


def test_stale_sync_answer_is_ignored():  # 재검토 I2
    z = FakeZoom(muted=False, readable=False); e = make_engine(z)
    e.mic.sync_estimate(False)                 # 추정: 해제(실제와 일치)
    token = e.sync_token()                     # 진행자가 대화상자를 엶
    e.tick()                                   # 그 사이 자동 음소거(Alt+A)
    assert z.muted is True
    assert e.sync_mic(False, token) is False   # 낡은 답은 반영하지 않음
    assert z.muted is True


def test_gate_closed_while_muted():
    z = FakeZoom(muted=True); e = make_engine(z); e.tick()
    assert e.mic_gate_open() is False


def test_gate_open_when_unmuted_and_confirmed():
    z = FakeZoom(muted=True); e = make_engine(z)
    zoom_for(e, 1.2, t0=0.0)
    assert e.mic_gate_open() is True


def test_gate_open_in_estimated_mode_when_unmuted():  # 녹화 RF5
    z = FakeZoom(muted=True, readable=False); e = make_engine(z); e.tick()
    zoom_for(e, 1.2, t0=0.0)
    assert e.mic_gate_open() is True


def test_gate_closed_after_emergency():
    z = FakeZoom(muted=True); e = make_engine(z)
    zoom_for(e, 1.2, t0=0.0); e.emergency_stop()
    assert e.mic_gate_open() is False


def test_meeting_present_tracks_last_known_state():
    z = FakeZoom(muted=True, active=False); e = make_engine(z)
    assert e.meeting_present() is None          # 아직 모름
    e.tick()
    assert e.meeting_present() is False
    z.active = True; e.clock.t += 1.0; e.tick()
    assert e.meeting_present() is True


def test_camera_changed_mutes_and_requires_new_history():
    z = FakeZoom(muted=True); e, log = make_engine_with_log(z)
    zoom_for(e, 1.2, t0=0.0)
    assert z.muted is False
    e.camera_changed()
    assert z.muted is True and log[-1] == "10:00:00 ZOOM→카메라변경 음소거 성공"
    e.on_stats(1.4, FaceStats(1, 0.3))
    assert z.muted is True                     # 새 카메라 이력이 1초 쌓이기 전에는 해제하지 않음
