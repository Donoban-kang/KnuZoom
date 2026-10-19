"""녹화 관리: 동의 확인 → FFmpeg 시작 → 음성 공급 → 자동 종료 감시 → 마무리(동의 기록·해시).

장치·프로세스·시계는 주입받아 Linux에서도 시험한다. 이 모듈의 오류는 음소거 제어로 전파하지 않는다.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from knuzoom.config import Settings
from knuzoom.recording import storage
from knuzoom.recording.audio_mix import BLOCK, SAMPLE_RATE, MicGate, mix, to_s16le
from knuzoom.recording.consent import ConsentRecord, render_text, validate
from knuzoom.recording.ffmpeg_cmd import build_command

MEETING_GONE_S = 10.0
STOP_WAIT_S = 10.0

W_LOOPBACK = "녹화: 스피커 소리 녹음 실패"
W_MIC = "녹화: 마이크 녹음 실패"
W_DISK = "녹화: 디스크 공간 부족으로 종료"
W_MEETING_GONE = "녹화: Zoom 회의가 끝나 종료"
W_FFMPEG = "녹화: FFmpeg 오류로 중단"
W_OVERLAY = "녹화: 녹화 중 표시 오류로 종료"


class AudioSource(Protocol):
    def read(self, frames: int) -> tuple[np.ndarray | None, np.ndarray | None]: ...
    def close(self) -> None: ...


class Proc(Protocol):
    stdin: object
    def poll(self) -> int | None: ...
    def wait(self, timeout: float) -> int: ...
    def kill(self) -> None: ...


class _NoAudio:
    def read(self, frames):
        return None, None

    def close(self):
        pass


@dataclass
class StartResult:
    ok: bool
    message: str
    path: Path | None = None


class Recorder:
    def __init__(self, s: Settings, *, ffmpeg: str | None,
                 spawn: Callable[[list[str]], Proc],
                 open_audio: Callable[[], AudioSource],
                 gate_open: Callable[[], bool],
                 meeting_active: Callable[[], bool],
                 set_filter: Callable[[Callable | None], None],
                 log: Callable[[str], None],
                 now: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 free_gb: Callable[[Path], float] = storage.free_gb,
                 overlay: Callable[[np.ndarray], np.ndarray] | None = None,
                 source: str = "screen",
                 threaded: bool = True) -> None:
        self.s = s
        self.ffmpeg = ffmpeg
        self.spawn = spawn
        self.open_audio = open_audio
        self.gate_open = gate_open
        self.meeting_active = meeting_active
        self.set_filter = set_filter
        self.log = log
        self.now = now
        self.monotonic = monotonic
        self.free_gb = free_gb
        self.overlay = overlay
        self.source = source
        self.threaded = threaded
        self._lock = threading.Lock()
        self.recording = False
        self.warning: str | None = None
        self.path: Path | None = None
        self._reset_session()

    def _reset_session(self) -> None:
        self._proc: Proc | None = None
        self._audio: AudioSource = _NoAudio()
        self._gate = MicGate()
        self._rec: ConsentRecord | None = None
        self._start: datetime | None = None
        self._t0 = 0.0
        self._gone_since: float | None = None
        self._warned: set[str] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── 시작 ─────────────────────────────────────────────────
    def start(self, rec: ConsentRecord) -> StartResult:
        with self._lock:
            if self.recording:
                return StartResult(False, "이미 녹화 중입니다")
            errors = validate(rec)
            if errors:
                return StartResult(False, errors[0])
            if self.overlay is None:  # 녹화 중 표시 없이 녹화하지 않는다
                return StartResult(False, "녹화를 시작할 수 없습니다: 녹화 중 표시를 만들 수 없습니다")
            if not self.ffmpeg:
                return StartResult(False, "녹화를 시작할 수 없습니다: FFmpeg를 찾을 수 없습니다")
            directory = storage.recording_dir(self.s)
            if self.free_gb(directory) < self.s.min_free_gb_start:
                return StartResult(False, "녹화를 시작할 수 없습니다: 디스크 여유 공간 부족"
                                          f"({self.s.min_free_gb_start:g}GB 미만)")
            self._reset_session()
            self.warning = None
            directory.mkdir(parents=True, exist_ok=True)
            self._start = self.now()
            self.path = storage.unique_path(directory, storage.safe_filename(rec.meeting, self._start))
            self._rec = rec
            self._write_record()
            self._proc = self.spawn(build_command(self.ffmpeg, self.path, self.s.recording_monitor,
                                                  self.s.recording_fps, self.source))
            try:
                self._audio = self.open_audio()
            except Exception:
                self._audio = _NoAudio()  # 소리 없이라도 화면은 녹화(경고는 pump에서)
            self.set_filter(self.overlay)
            self._t0 = self.monotonic()
            self.recording = True
            if self.threaded:
                self._thread = threading.Thread(target=self._pump_loop, daemon=True, name="knuzoom-rec-audio")
                self._thread.start()
        self.log(f"{self.now():%H:%M:%S} 녹화 시작 {self.path.name}")
        return StartResult(True, "", self.path)

    # ── 음성 공급 ─────────────────────────────────────────────
    def _warn_once(self, w: str) -> None:
        if w not in self._warned:
            self._warned.add(w)
            self.warning = w

    def pump_once(self) -> bool:
        """음성 1블록을 FFmpeg에 쓴다. 장치에서 아무것도 못 받았으면 False(호출 측이 시간을 맞춘다)."""
        try:
            loop, mic = self._audio.read(BLOCK)
        except Exception:
            loop, mic = None, None
            self._warn_once(W_LOOPBACK)
        else:
            if loop is None:
                self._warn_once(W_LOOPBACK)
            if mic is None:
                self._warn_once(W_MIC)
        try:
            open_ = bool(self.gate_open())
        except Exception:
            open_ = False
        gated = self._gate.process(mic, open_) if mic is not None else None
        try:
            self._proc.stdin.write(to_s16le(mix(loop, gated)))
        except (OSError, ValueError, AttributeError):
            pass  # FFmpeg가 끝났으면 tick()이 감지한다
        return loop is not None or mic is not None

    def _pump_loop(self) -> None:
        block_s = BLOCK / SAMPLE_RATE
        next_t = time.monotonic()
        while not self._stop_event.is_set():
            got_device_audio = self.pump_once()
            if not got_device_audio:  # 장치가 박자를 맞춰 주지 않으면 직접 20ms 간격 유지
                next_t += block_s
                time.sleep(max(0.0, next_t - time.monotonic()))
            else:
                next_t = time.monotonic()

    # ── 감시 ─────────────────────────────────────────────────
    @property
    def elapsed_s(self) -> float:
        return self.monotonic() - self._t0 if self.recording else 0.0

    def tick(self) -> None:
        """UI 주기마다 호출: FFmpeg 종료, 회의 종료, 디스크 부족을 감지해 자동 종료."""
        if not self.recording:
            return
        if self._proc.poll() is not None:
            self._auto_stop("FFmpeg 오류", W_FFMPEG)
            return
        try:
            active = self.meeting_active()
        except Exception:
            active = True  # 확인 실패만으로 녹화를 끊지 않는다
        now = self.monotonic()
        if active:
            self._gone_since = None
        elif self._gone_since is None:
            self._gone_since = now
        elif now - self._gone_since >= MEETING_GONE_S:
            self._auto_stop("회의 종료", W_MEETING_GONE)
            return
        if self.free_gb(self.path.parent) < self.s.min_free_gb_stop:
            self._auto_stop("디스크 부족", W_DISK)

    def on_overlay_error(self, exc: Exception) -> None:
        """녹화 중 표시를 못 하면 비밀 녹화가 되지 않도록 녹화를 멈춘다(카메라 스레드에서 호출될 수 있음)."""
        self._auto_stop("표시 오류", W_OVERLAY)

    def _auto_stop(self, reason: str, warning: str) -> None:
        self.stop(reason)
        self.warning = warning

    # ── 종료 ─────────────────────────────────────────────────
    def stop(self, reason: str = "사용자 종료") -> Path | None:
        with self._lock:
            if not self.recording:
                return None
            self.recording = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        try:
            self._proc.stdin.close()  # -shortest: 음성 입력이 끝나면 FFmpeg가 파일을 마무리
        except Exception:
            pass
        try:
            self._proc.wait(timeout=STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        except Exception:
            pass
        self.set_filter(None)
        try:
            self._audio.close()
        except Exception:
            pass
        end = self.now()
        sha = storage.sha256_file(self.path) if self.path.exists() else "(파일 없음)"
        self._write_record(end, sha)
        self.log(f"{end:%H:%M:%S} 녹화 종료({reason}) {self.path.name}")
        return self.path

    def _write_record(self, end: datetime | None = None, sha: str | None = None) -> None:
        storage.record_path(self.path).write_text(
            render_text(self._rec, self._start, self.path.name, end, sha), encoding="utf-8")
