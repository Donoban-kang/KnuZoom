"""녹화 관리: 동의 확인 → FFmpeg 시작 → 음성 공급 → 자동 종료 감시 → 마무리(동의 기록·해시).

장치·프로세스·시계는 주입받아 Linux에서도 시험한다. 이 모듈의 오류는 음소거 제어로 전파하지 않는다.
녹화 한 번의 상태는 _Session에 모아 두어, 마무리 중인 이전 녹화와 새 녹화가 섞이지 않게 한다.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
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
PUMP_JOIN_S = 2.0
GATE_OPEN_DELAY_S = 1.0  # 해제 직후 장치 버퍼에 남아 있던 '해제 전' 마이크 소리가 섞이지 않게 열림을 늦춘다

W_LOOPBACK = "녹화: 스피커 소리 녹음 실패"
W_MIC = "녹화: 마이크 녹음 실패"
W_DISK = "녹화: 디스크 공간 부족으로 종료"
W_MEETING_GONE = "녹화: Zoom 회의가 끝나 종료"
W_FFMPEG = "녹화: FFmpeg 오류로 중단"
W_OVERLAY = "녹화: 녹화 중 표시 오류로 종료"
W_OVERLAY_GONE = "녹화: 녹화 중 표시를 내보낼 수 없어 종료"


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


@dataclass
class _Session:
    rec: ConsentRecord
    start: datetime
    path: Path
    proc: Proc
    audio: AudioSource = field(default_factory=_NoAudio)
    gate: MicGate = field(default_factory=MicGate)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    t0: float = 0.0
    gone_since: float | None = None
    open_since: float | None = None


class Recorder:
    def __init__(self, s: Settings, *, ffmpeg: str | None,
                 spawn: Callable[[list[str]], Proc],
                 open_audio: Callable[[], AudioSource],
                 gate_open: Callable[[], bool],
                 meeting_active: Callable[[], bool],
                 set_filter: Callable[[Callable | None], None],
                 log: Callable[[str], None],
                 overlay_factory: Callable[[str], Callable[[np.ndarray], np.ndarray]] | None,
                 overlay_alive: Callable[[], bool] = lambda: True,
                 now: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 free_gb: Callable[[Path], float] = storage.free_gb,
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
        self.overlay_factory = overlay_factory
        self.overlay_alive = overlay_alive
        self.now = now
        self.monotonic = monotonic
        self.free_gb = free_gb
        self.source = source
        self.threaded = threaded
        self._lock = threading.Lock()
        self._session: _Session | None = None
        self._finalizer: threading.Thread | None = None
        self._warned: set[str] = set()
        self.warning: str | None = None

    # ── 상태 ─────────────────────────────────────────────────
    @property
    def recording(self) -> bool:
        return self._session is not None

    @property
    def finalizing(self) -> bool:
        return self._finalizer is not None and self._finalizer.is_alive()

    @property
    def path(self) -> Path | None:
        s = self._session
        return s.path if s else None

    @property
    def elapsed_s(self) -> float:
        s = self._session
        return self.monotonic() - s.t0 if s else 0.0

    def wait_finalized(self, timeout: float | None = None) -> bool:
        f = self._finalizer
        if f is not None:
            f.join(timeout)
        return not self.finalizing

    def _log(self, line: str) -> None:
        try:
            self.log(line)
        except Exception:
            pass  # 로그 실패가 녹화 시작·종료를 깨뜨리지 않게

    # ── 시작 ─────────────────────────────────────────────────
    def start(self, rec: ConsentRecord) -> StartResult:
        with self._lock:
            if self._session is not None:
                return StartResult(False, "이미 녹화 중입니다")
            if self.finalizing:
                return StartResult(False, "이전 녹화를 마무리하는 중입니다. 잠시 후 다시 시도해 주세요")
            errors = validate(rec)
            if errors:
                return StartResult(False, errors[0])
            try:  # 표시는 녹화 시작 때 '지금' 기관 이름으로 만든다
                overlay = self.overlay_factory(self.s.site_name) if self.overlay_factory else None
            except Exception:
                overlay = None
            if overlay is None:  # 녹화 중 표시 없이 녹화하지 않는다
                return StartResult(False, "녹화를 시작할 수 없습니다: 녹화 중 표시를 만들 수 없습니다")
            if not self.overlay_alive():
                return StartResult(False, "녹화를 시작할 수 없습니다: 가상 카메라로 영상을 보내지 못하고 있습니다")
            if not self.ffmpeg:
                return StartResult(False, "녹화를 시작할 수 없습니다: FFmpeg를 찾을 수 없습니다")
            directory = storage.recording_dir(self.s)
            if self.free_gb(directory) < self.s.min_free_gb_start:
                return StartResult(False, "녹화를 시작할 수 없습니다: 디스크 여유 공간 부족"
                                          f"({self.s.min_free_gb_start:g}GB 미만)")
            self.warning = None
            self._warned = set()
            directory.mkdir(parents=True, exist_ok=True)
            start = self.now()
            path = storage.unique_path(directory, storage.safe_filename(rec.meeting, start))
            storage.record_path(path).write_text(render_text(rec, start, path.name), encoding="utf-8")
            proc = self.spawn(build_command(self.ffmpeg, path, self.s.recording_monitor,
                                            self.s.recording_fps, self.source))
            sess = _Session(rec=rec, start=start, path=path, proc=proc, t0=self.monotonic())
            try:
                sess.audio = self.open_audio()
            except Exception:
                sess.audio = _NoAudio()  # 소리 없이라도 화면은 녹화(경고는 pump에서)
            self.set_filter(overlay)
            self._session = sess
            if self.threaded:
                sess.thread = threading.Thread(target=self._pump_loop, args=(sess,), daemon=True,
                                               name="knuzoom-rec-audio")
                sess.thread.start()
        self._log(f"{start:%H:%M:%S} 녹화 시작 {path.name}")
        return StartResult(True, "", path)

    # ── 음성 공급 ─────────────────────────────────────────────
    def _warn_once(self, w: str) -> None:
        if w not in self._warned:
            self._warned.add(w)
            self.warning = w

    def pump_once(self, sess: _Session | None = None) -> bool:
        """음성 1블록을 FFmpeg에 쓴다. 장치에서 아무것도 못 받았으면 False(호출 측이 시간을 맞춘다)."""
        sess = sess or self._session
        if sess is None:
            return False
        try:
            loop, mic = sess.audio.read(BLOCK)
        except Exception:
            loop, mic = None, None
            self._warn_once(W_LOOPBACK)
        else:
            if loop is None:
                self._warn_once(W_LOOPBACK)
            if mic is None:
                self._warn_once(W_MIC)
        try:
            eligible = bool(self.gate_open())
        except Exception:
            eligible = False
        now = self.monotonic()
        if eligible:
            if sess.open_since is None:
                sess.open_since = now
            open_ = now - sess.open_since >= GATE_OPEN_DELAY_S
        else:  # 닫힘은 즉시
            sess.open_since = None
            open_ = False
        gated = sess.gate.process(mic, open_) if mic is not None else None
        try:
            sess.proc.stdin.write(to_s16le(mix(loop, gated)))
        except (OSError, ValueError, AttributeError):
            pass  # FFmpeg가 끝났으면 tick()이 감지한다
        return loop is not None or mic is not None

    def _pump_loop(self, sess: _Session) -> None:
        block_s = BLOCK / SAMPLE_RATE
        next_t = time.monotonic()
        while not sess.stop_event.is_set():
            got_device_audio = self.pump_once(sess)
            if not got_device_audio:  # 장치가 박자를 맞춰 주지 않으면 직접 20ms 간격 유지
                next_t += block_s
                time.sleep(max(0.0, next_t - time.monotonic()))
            else:
                next_t = time.monotonic()

    # ── 감시 ─────────────────────────────────────────────────
    def tick(self) -> None:
        """UI 주기마다 호출: FFmpeg 종료, 표시 송출 중단, 회의 종료, 디스크 부족을 감지해 자동 종료."""
        sess = self._session
        if sess is None:
            return
        if sess.proc.poll() is not None:
            self._auto_stop("FFmpeg 오류", W_FFMPEG)
            return
        try:
            alive = self.overlay_alive()
        except Exception:
            alive = False
        if not alive:  # 다른 기관이 '녹화 중' 표시를 볼 수 없으면 비밀 녹화가 되므로 멈춘다
            self._auto_stop("표시 송출 중단", W_OVERLAY_GONE)
            return
        try:
            active = self.meeting_active()
        except Exception:
            active = True  # 확인 실패만으로 녹화를 끊지 않는다
        now = self.monotonic()
        if active:
            sess.gone_since = None
        elif sess.gone_since is None:
            sess.gone_since = now
        elif now - sess.gone_since >= MEETING_GONE_S:
            self._auto_stop("회의 종료", W_MEETING_GONE)
            return
        if self.free_gb(sess.path.parent) < self.s.min_free_gb_stop:
            self._auto_stop("디스크 부족", W_DISK)

    def on_overlay_error(self, exc: Exception) -> None:
        """녹화 중 표시를 못 하면 비밀 녹화가 되지 않도록 녹화를 멈춘다(카메라 스레드에서 호출될 수 있음)."""
        self._auto_stop("표시 오류", W_OVERLAY)

    def _auto_stop(self, reason: str, warning: str) -> None:
        if self.stop(reason) is not None:
            self.warning = warning

    # ── 종료 ─────────────────────────────────────────────────
    def stop(self, reason: str = "사용자 종료") -> Path | None:
        """녹화를 멈춘다(멱등). 표시를 즉시 끄고, 시간이 걸리는 마무리는 threaded면 백그라운드에서 한다."""
        with self._lock:
            sess = self._session
            if sess is None:
                return None
            self._session = None
            sess.stop_event.set()
            self.set_filter(None)
            if self.threaded:
                self._finalizer = threading.Thread(target=self._finalize, args=(sess, reason), daemon=True,
                                                   name="knuzoom-rec-finalize")
                self._finalizer.start()
        if not self.threaded:
            self._finalize(sess, reason)
        return sess.path

    def _finalize(self, sess: _Session, reason: str) -> None:
        if sess.thread is not None:
            sess.thread.join(timeout=PUMP_JOIN_S)
            if sess.thread.is_alive():
                # 음성 스레드가 파이프 쓰기에서 막혀 있음(FFmpeg가 읽지 않음) → 먼저 종료시켜 막힘을 푼다
                self._kill(sess)
                sess.thread.join(timeout=PUMP_JOIN_S)
        try:
            sess.proc.stdin.close()  # -shortest: 음성 입력이 끝나면 FFmpeg가 파일을 마무리
        except Exception:
            pass
        try:
            sess.proc.wait(timeout=STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            self._kill(sess)
        except Exception:
            pass
        try:
            sess.audio.close()
        except Exception:
            pass
        end = self.now()
        try:
            sha = storage.sha256_file(sess.path) if sess.path.exists() else "(파일 없음)"
        except OSError:
            sha = "(계산 실패)"
        try:
            storage.record_path(sess.path).write_text(
                render_text(sess.rec, sess.start, sess.path.name, end, sha), encoding="utf-8")
        except OSError:
            pass
        self._log(f"{end:%H:%M:%S} 녹화 종료({reason}) {sess.path.name}")

    @staticmethod
    def _kill(sess: _Session) -> None:
        try:
            sess.proc.kill()
        except Exception:
            pass
