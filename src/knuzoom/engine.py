"""판정·확정·마이크 제어를 묶고 오류 정책을 적용한다."""
from __future__ import annotations

import threading
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
_MIC_WARNINGS = {W_WAITING, W_BLOCKED, W_MUTE_FAILED, W_ESTIMATED}


@dataclass
class Status:
    muted: bool
    verdict: Verdict
    n: int
    h: float
    auto: bool
    warning: str | None


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
                 run: Callable[[Callable[[], None]], None] = lambda f: f()) -> None:
        # run: 마이크 제어(최대 약 2초 대기)를 실행할 곳. 실제 앱에서는 전용 작업 스레드를 넘겨
        # 카메라 스레드의 영상 송출이 멈추지 않게 한다. 기본값은 즉시 실행(시험용).
        self.s = s
        self.mic = mic
        self.log = log
        self.clock_hms = clock_hms
        self.run = run
        self.stab = Stabilizer(s)
        self._lock = threading.RLock()
        self._muted = True
        self._pending = True
        self._auto = True
        self._warning: str | None = None
        self._last = (Verdict.UNCERTAIN, 0, 0.0)
        self._calib_kind: str | None = None
        self._calib_start = 0.0
        self._calib_samples: list[float] = []
        self._calib_h: dict[str, float | None] = {"wide": None, "zoom": None}

    # ── 마이크 적용 ──────────────────────────────────────────
    def _request(self, want_muted: bool, log_prefix: str | None) -> None:
        self._pending = False
        self.run(lambda: self._apply(want_muted, log_prefix))

    def _apply(self, want_muted: bool, log_prefix: str | None) -> None:
        r = self.mic.apply(want_muted)
        with self._lock:
            if r is ApplyResult.NO_MEETING:
                self._pending = True
                self._set_mic_warning(W_WAITING)
            elif r is ApplyResult.OK:
                self._set_mic_warning(None)
            elif r is ApplyResult.ESTIMATED:
                self._set_mic_warning(W_ESTIMATED)
            elif r is ApplyResult.BLOCKED:
                self._set_mic_warning(W_BLOCKED)
            else:
                self._set_mic_warning(W_MUTE_FAILED)
        if log_prefix is not None:
            self.log(f"{self.clock_hms()} {log_prefix} {_result_text(want_muted, r)}")

    def _set_mic_warning(self, w: str | None) -> None:
        # 카메라·오류·보정 경고는 마이크 결과로 덮어쓰지 않는다.
        if self._warning is None or self._warning in _MIC_WARNINGS:
            self._warning = w

    # ── 입력 ─────────────────────────────────────────────────
    def on_stats(self, t: float, stats: FaceStats) -> None:
        with self._lock:
            if self._warning == W_CAMERA_LOST:
                self._warning = None
            v = classify(stats, self.s)
            self._last = (v, stats.n, stats.h)
            self._collect_calibration(t, stats)
            if self._pending:
                self._request(self._muted, None)
            prev = self.stab.state
            new = self.stab.update(t, v)
            if new is not None and self._auto:
                self._muted = new is Verdict.WIDE
                self._request(self._muted, f"{prev.value}→{new.value}")

    def tick(self) -> None:
        with self._lock:
            if self._pending:
                self._request(self._muted, None)

    def on_camera_lost(self, t: float) -> None:
        with self._lock:
            prev = self.stab.state
            self.stab.reset(t)
            self._muted = True
            self._warning = W_CAMERA_LOST
            self._request(True, f"{prev.value}→카메라끊김")

    def on_error(self, exc: Exception) -> None:
        with self._lock:
            self._muted = True
            self._warning = W_ERROR
            self._request(True, None)

    def set_auto(self, on: bool) -> None:
        with self._lock:
            self._auto = on
            if on:
                if self._warning == W_ERROR:
                    self._warning = None  # 진행자가 자동을 다시 켜면 오류 경고를 확인한 것으로 본다
                self._muted = self.stab.state is Verdict.WIDE
                self._request(self._muted, None)

    def emergency_stop(self) -> None:
        with self._lock:
            prev = self.stab.state
            self._auto = False
            self._muted = True
            self._request(True, f"{prev.value}→긴급정지")

    def sync_mic(self, muted: bool) -> None:
        with self._lock:
            self.mic.sync_estimate(muted)

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
        self._calib_h[self._calib_kind] = median_h(self._calib_samples)
        self._calib_kind = None
        if self._calib_h["wide"] is None or self._calib_h["zoom"] is None:
            return
        th = compute_thresholds(self._calib_h["wide"], self._calib_h["zoom"])
        self._calib_h = {"wide": None, "zoom": None}
        if th is None:
            self._warning = W_CALIBRATION
            return
        self.s.wide_h, self.s.zoom_h = th
        if self._warning == W_CALIBRATION:
            self._warning = None

    def calibration_running(self) -> bool:
        with self._lock:
            return self._calib_kind is not None

    # ── 표시 ─────────────────────────────────────────────────
    def status(self) -> Status:
        with self._lock:
            v, n, h = self._last
            return Status(self._muted, v, n, h, self._auto, self._warning)
