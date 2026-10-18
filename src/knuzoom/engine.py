"""판정·확정·마이크 제어를 묶고 오류 정책을 적용한다."""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal

from knuzoom.calibration import compute_thresholds, median_h
from knuzoom.config import Settings
from knuzoom.detector import FaceStats, Verdict, classify
from knuzoom.mic import ApplyResult, MicController
from knuzoom.stabilizer import Stabilizer

W_WAITING = "대기"
W_BLOCKED = "호스트(A대학)가 해제를 막았을 수 있음"
W_MUTE_FAILED = "음소거 실패"
W_ESTIMATED = "상태 추정 중(Zoom 상태를 읽을 수 없음)"
W_CAMERA_LOST = "카메라 끊김"
W_ERROR = "오류 발생"
W_CALIBRATION = "보정 실패: 확대 장면이 넓은 장면보다 커야 합니다"
W_CALIB_NO_FACE = "보정 실패: 얼굴이 검출되지 않았습니다"
W_CALIB_SMALL_GAP = "보정 실패: 넓은 장면과 확대 장면의 차이가 너무 작습니다"
_CALIB_WARNINGS = {W_CALIBRATION, W_CALIB_NO_FACE, W_CALIB_SMALL_GAP}
W_EMERGENCY_HOLD = "긴급 정지 후 대기: 넓은 장면을 거쳐 다시 확대되면 자동 해제"
_MIC_WARNINGS = {W_WAITING, W_BLOCKED, W_MUTE_FAILED, W_ESTIMATED}


# 시간 상수(초)
CAMERA_WATCHDOG_S = 2.0   # 분석 결과가 이만큼 끊기면 카메라 끊김으로 본다(첫 결과 이후부터)
PENDING_RETRY_S = 1.0     # 확인되지 않은 마이크 상태를 다시 맞추는 간격
PRESENCE_CHECK_S = 2.0    # 회의 퇴장/재입장을 확인하는 간격
ERROR_THROTTLE_S = 1.0    # 같은 오류가 반복될 때 처리 간격


@dataclass
class Status:
    muted: bool
    verdict: Verdict
    n: int
    h: float
    auto: bool
    warning: str | None
    confirmed: bool = False  # Zoom에서 실제로 그 상태임을 확인했는지


def _result_text(want_muted: bool, r: ApplyResult) -> str:
    if r is ApplyResult.OK:
        return "음소거 성공" if want_muted else "해제 성공"
    return {
        ApplyResult.BLOCKED: "해제 차단",
        ApplyResult.FAILED: "음소거 실패",
        ApplyResult.NO_MEETING: "대기",
        ApplyResult.ESTIMATED: "추정 적용",
    }[r]


class Engine:
    def __init__(self, s: Settings, mic: MicController, log: Callable[[str], None],
                 clock_hms: Callable[[], str],
                 run: Callable[[Callable[[], None]], None] = lambda f: f(),
                 clock: Callable[[], float] = time.monotonic) -> None:
        # run: 마이크 제어(최대 수 초 대기)를 실행할 곳. 실제 앱에서는 전용 작업 스레드를 넘겨
        # 카메라 스레드의 영상 송출이 멈추지 않게 한다. 기본값은 즉시 실행(시험용).
        self.s = s
        self.mic = mic
        self.log = log
        self.clock_hms = clock_hms
        self.run = run
        self.clock = clock
        self.stab = Stabilizer(s)
        self._lock = threading.RLock()
        self._muted = True
        self._pending = True
        self._auto = True
        # 긴급 정지 당시 확대돼 있던 발언자는, 넓은 장면을 거친 새 확대 전까지 해제하지 않는다.
        self._emergency_hold = False
        self._warning: str | None = None
        self._confirmed = False
        self._last = (Verdict.UNCERTAIN, 0, 0.0)
        # 요청 병합: 작업 스레드에는 항상 "가장 최근 원하는 상태" 하나만 남긴다.
        self._slot: tuple[bool, str | None] | None = None
        self._job_scheduled = False
        self._last_request_at = -math.inf
        self._last_stats_at: float | None = None
        self._camera_lost = False
        self._meeting_present: bool | None = None
        self._last_presence_check = clock()
        self._last_error_at = -math.inf
        self._calib_kind: str | None = None
        self._calib_start = 0.0
        self._calib_samples: list[float] = []
        self._calib_h: dict[str, float | None] = {"wide": None, "zoom": None}

    # ── 마이크 적용 ──────────────────────────────────────────
    def _request(self, want_muted: bool, log_prefix: str | None) -> None:
        self._pending = False
        self._confirmed = False
        self._slot = (want_muted, log_prefix)
        self._last_request_at = self.clock()
        if not self._job_scheduled:
            self._job_scheduled = True
            self.run(self._drain)

    def _drain(self) -> None:
        while True:
            with self._lock:
                if self._slot is None:
                    self._job_scheduled = False
                    return
                want_muted, log_prefix = self._slot
                self._slot = None
            self._apply(want_muted, log_prefix)

    def _apply(self, want_muted: bool, log_prefix: str | None) -> None:
        r = self.mic.apply(want_muted)
        with self._lock:
            self._meeting_present = r is not ApplyResult.NO_MEETING
            if want_muted == self._muted and self._slot is None:  # 최신 요청의 결과일 때만 반영
                if r is ApplyResult.OK:
                    self._confirmed = True
                    self._set_mic_warning(None)
                elif r is ApplyResult.NO_MEETING:
                    self._pending = True
                    self._set_mic_warning(W_WAITING)
                elif r is ApplyResult.ESTIMATED:
                    self._pending = True  # 상태를 읽을 수 있게 되면(오디오 연결 등) 실제 상태로 다시 맞춘다
                    self._set_mic_warning(W_ESTIMATED)
                elif r is ApplyResult.BLOCKED:
                    self._set_mic_warning(W_BLOCKED)
                else:
                    self._pending = True  # 음소거 실패는 계속 재시도한다
                    self._set_mic_warning(W_MUTE_FAILED)
        if log_prefix is not None:
            self.log(f"{self.clock_hms()} {log_prefix} {_result_text(want_muted, r)}")

    def _set_mic_warning(self, w: str | None) -> None:
        # 카메라·오류·보정 경고는 마이크 결과로 덮어쓰지 않는다.
        if self._warning is None or self._warning in _MIC_WARNINGS:
            self._warning = w

    def _check_presence(self) -> None:
        active = self.mic.adapter.meeting_active()
        with self._lock:
            if active and self._meeting_present is False:
                self._pending = True  # 회의 재입장: 현재 원하는 상태를 다시 적용
            self._meeting_present = active

    # ── 입력 ─────────────────────────────────────────────────
    def on_stats(self, t: float, stats: FaceStats) -> None:
        with self._lock:
            self._last_stats_at = self.clock()
            if self._camera_lost:
                self._camera_lost = False
                if self._warning == W_CAMERA_LOST:
                    self._warning = None
            v = classify(stats, self.s)
            self._last = (v, stats.n, stats.h)
            self._collect_calibration(t, stats)
            prev = self.stab.state
            new = self.stab.update(t, v)
            if new is Verdict.WIDE and self._emergency_hold:
                self._emergency_hold = False
                if self._warning == W_EMERGENCY_HOLD:
                    self._warning = None
            if new is Verdict.ZOOM and self._emergency_hold:
                return
            if new is not None and self._auto:
                self._muted = new is Verdict.WIDE
                self._request(self._muted, f"{prev.value}→{new.value}")

    def tick(self) -> None:
        """UI 루프가 주기적으로(약 200ms) 호출한다."""
        now = self.clock()
        with self._lock:
            if (self._last_stats_at is not None and not self._camera_lost
                    and now - self._last_stats_at > CAMERA_WATCHDOG_S):
                self._lose_camera()  # 카메라 스레드가 멈췄거나 죽음
            if self._pending:
                if now - self._last_request_at >= PENDING_RETRY_S:
                    self._request(self._muted, None)
            elif not self._job_scheduled and now - self._last_presence_check >= PRESENCE_CHECK_S:
                self._last_presence_check = now
                self.run(self._check_presence)

    def _lose_camera(self) -> None:
        prev = self.stab.state
        self.stab.reset(self.clock())
        self._camera_lost = True
        self._muted = True
        self._warning = W_CAMERA_LOST
        self._request(True, f"{prev.value}→카메라끊김")

    def on_camera_lost(self, t: float) -> None:
        with self._lock:
            if not self._camera_lost:
                self._lose_camera()

    def on_error(self, exc: Exception) -> None:
        now = self.clock()
        with self._lock:
            if self._warning == W_ERROR and now - self._last_error_at < ERROR_THROTTLE_S:
                return
            self._last_error_at = now
            self.stab.reset(now)
            self._muted = True
            self._warning = W_ERROR
            self.log(f"{self.clock_hms()} 오류: {type(exc).__name__}: {exc}")
            self._request(True, None)

    def set_auto(self, on: bool) -> None:
        with self._lock:
            self._auto = on
            if on:
                if self._warning == W_ERROR:
                    self._warning = None  # 진행자가 자동을 다시 켜면 오류 경고를 확인한 것으로 본다
                self._muted = self._emergency_hold or self.stab.state is Verdict.WIDE
                self._request(self._muted, None)

    def emergency_stop(self) -> None:
        with self._lock:
            prev = self.stab.state
            if prev is Verdict.ZOOM:
                self._emergency_hold = True
                if self._warning is None or self._warning in _MIC_WARNINGS:
                    self._warning = W_EMERGENCY_HOLD
            self._auto = False
            self._muted = True
            self._request(True, f"{prev.value}→긴급정지")

    def sync_mic(self, muted: bool) -> None:
        """[상태 맞추기]: 진행자가 알려준 실제 상태로 추정을 고치고, 원하는 상태로 다시 맞춘다."""
        self.mic.sync_estimate(muted)  # 진행 중인 제어가 끝날 때까지 기다릴 수 있으므로 엔진 잠금 밖에서
        with self._lock:
            self._request(self._muted, None)

    def shutdown(self) -> None:
        """종료 직전 호출: 남은 요청을 버리고 즉시(동기) 음소거한다."""
        with self._lock:
            self._auto = False
            self._slot = None
            self._muted = True
        r = self.mic.apply(True)
        self.log(f"{self.clock_hms()} 종료 {_result_text(True, r)}")

    # ── 보정 ─────────────────────────────────────────────────
    def start_calibration(self, kind: Literal["wide", "zoom"], t: float) -> None:
        with self._lock:
            self._calib_kind = kind
            self._calib_start = t
            self._calib_samples = []

    def _collect_calibration(self, t: float, stats: FaceStats) -> None:
        if self._calib_kind is None:
            return
        if t <= self._calib_start + self.s.calibration_sample_s + 1e-9:
            if stats.n >= 1:
                self._calib_samples.append(stats.h)
            return
        h = median_h(self._calib_samples)
        self._calib_h[self._calib_kind] = h
        self._calib_kind = None
        if h is None:
            self._warning = W_CALIB_NO_FACE
            return
        h_wide, h_zoom = self._calib_h["wide"], self._calib_h["zoom"]
        if h_wide is None or h_zoom is None:
            return
        self._calib_h = {"wide": None, "zoom": None}
        th = compute_thresholds(h_wide, h_zoom)
        if th is None:
            self._warning = W_CALIBRATION if h_zoom <= h_wide else W_CALIB_SMALL_GAP
            return
        self.s.wide_h, self.s.zoom_h = th
        if self._warning in _CALIB_WARNINGS:
            self._warning = None

    def calibration_running(self) -> bool:
        with self._lock:
            return self._calib_kind is not None

    # ── 표시 ─────────────────────────────────────────────────
    def status(self) -> Status:
        with self._lock:
            v, n, h = self._last
            return Status(self._muted, v, n, h, self._auto, self._warning, self._confirmed)
