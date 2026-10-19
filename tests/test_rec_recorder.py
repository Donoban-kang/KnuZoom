import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

from knuzoom.config import Settings
from knuzoom.recording.consent import ConsentRecord
from knuzoom.recording.recorder import Recorder
from knuzoom.recording.storage import sha256_file


class FakeStdin:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, b):
        if self.closed:
            raise ValueError("closed")
        self.data += b

    def close(self):
        self.closed = True


class FakeProc:
    def __init__(self, hang=False):
        self.stdin = FakeStdin()
        self.code = None
        self.hang = hang
        self.killed = False

    def poll(self):
        return self.code

    def wait(self, timeout):
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return 0

    def kill(self):
        self.killed = True


class FakeAudio:
    def __init__(self, loop=0.0, mic=1.0, fail=False):
        self.loop, self.mic, self.fail, self.closed = loop, mic, fail, False

    def read(self, frames):
        if self.fail:
            raise OSError("device")
        blk = lambda v: None if v is None else np.full((frames, 2), v, np.float32)
        return blk(self.loop), blk(self.mic)

    def close(self):
        self.closed = True


def consent(**kw):
    base = dict(meeting="회의", site_name="B대학", required_parties=["A대학"], agreed_parties=["A대학"],
                method="사전 공문", method_other="", purpose="회의록 작성", retention_days=30)
    return ConsentRecord(**{**base, **kw})


class Env:
    def __init__(self, tmp_path, **kw):
        self.proc = kw.pop("proc", FakeProc())
        self.audio = kw.pop("audio", FakeAudio())
        self.gate = kw.pop("gate", True)
        self.meeting = True
        self.free = kw.pop("free", 100.0)
        self.mono = 0.0
        self.filters, self.logs, self.spawned, self.names = [], [], [], []
        self.alive = True
        self.rec = Recorder(
            Settings(recording_dir=str(tmp_path)), ffmpeg=kw.pop("ffmpeg", "ffmpeg"),
            spawn=lambda cmd: (self.spawned.append(cmd), self.proc)[1],
            open_audio=lambda: self.audio, gate_open=lambda: self.gate,
            meeting_active=lambda: self.meeting, set_filter=self.filters.append, log=self.logs.append,
            now=lambda: datetime(2026, 10, 19, 14, 0, 5), monotonic=lambda: self.mono,
            free_gb=lambda p: self.free, overlay_factory=lambda name: (self.names.append(name), (lambda f: f))[1],
            overlay_alive=lambda: self.alive, threaded=False)


def test_start_requires_valid_consent(tmp_path):
    env = Env(tmp_path)
    r = env.rec.start(consent(agreed_parties=[]))
    assert r.ok is False and r.message.startswith("동의하지 않은 기관") and env.spawned == []


def test_start_refuses_low_disk(tmp_path):
    env = Env(tmp_path, free=4.9)
    r = env.rec.start(consent())
    assert r.message == "녹화를 시작할 수 없습니다: 디스크 여유 공간 부족(5GB 미만)" and env.spawned == []


def test_start_refuses_missing_ffmpeg(tmp_path):
    env = Env(tmp_path, ffmpeg=None)
    assert env.rec.start(consent()).message == "녹화를 시작할 수 없습니다: FFmpeg를 찾을 수 없습니다"


def test_start_writes_record_and_sets_filter(tmp_path):
    env = Env(tmp_path)
    r = env.rec.start(consent())
    assert r.ok and r.path == tmp_path / "20261019_1400_회의.mp4" and env.rec.recording
    txt = (tmp_path / "20261019_1400_회의.txt").read_text(encoding="utf-8")
    assert "녹화 종료: (녹화 중)" in txt
    assert callable(env.filters[-1])
    assert env.spawned[0][-1] == str(r.path)


def test_second_start_refused(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    assert env.rec.start(consent()).message == "이미 녹화 중입니다"


def test_pump_writes_one_block(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    env.rec.pump_once()
    assert len(env.proc.stdin.data) == 960 * 2 * 2


def test_mic_excluded_when_gate_closed(tmp_path):
    env = Env(tmp_path, audio=FakeAudio(loop=0.0, mic=1.0), gate=False)
    env.rec.start(consent())
    env.rec.pump_once()
    assert set(env.proc.stdin.data) == {0}


def test_audio_read_error_continues_with_silence_and_warns(tmp_path):  # RF3
    env = Env(tmp_path, audio=FakeAudio(fail=True))
    env.rec.start(consent())
    env.rec.pump_once()
    assert len(env.proc.stdin.data) == 3840 and set(env.proc.stdin.data) == {0}
    assert env.rec.warning == "녹화: 스피커 소리 녹음 실패" and env.rec.recording


def test_missing_mic_warns_once_and_records_loopback(tmp_path):
    env = Env(tmp_path, audio=FakeAudio(loop=0.5, mic=None))
    env.rec.start(consent())
    env.rec.pump_once()
    samples = np.frombuffer(bytes(env.proc.stdin.data), "<i2")
    assert np.all(np.abs(samples.astype(int) - 16384) <= 1)
    assert env.rec.warning == "녹화: 마이크 녹음 실패"


def test_auto_stop_when_meeting_gone_10s(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    env.meeting = False
    env.rec.tick()
    env.mono = 9.9
    env.rec.tick()
    assert env.rec.recording
    env.mono = 10.5
    env.rec.tick()
    assert not env.rec.recording and env.rec.warning == "녹화: Zoom 회의가 끝나 종료"


def test_auto_stop_on_low_disk(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    env.free = 1.9
    env.rec.tick()
    assert not env.rec.recording and env.rec.warning == "녹화: 디스크 공간 부족으로 종료"


def test_ffmpeg_exit_detected(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    env.proc.code = 1
    env.rec.tick()
    assert not env.rec.recording and env.rec.warning == "녹화: FFmpeg 오류로 중단"


def test_stop_is_idempotent_and_finalizes_record(tmp_path):  # RF4
    env = Env(tmp_path)
    path = env.rec.start(consent()).path
    path.write_bytes(b"abc")
    assert env.rec.stop("프로그램 종료") == path
    assert env.rec.stop() is None
    txt = path.with_suffix(".txt").read_text(encoding="utf-8")
    assert f"SHA-256: {sha256_file(path)}" in txt and "녹화 종료: 2026-10-19 14:00:05" in txt
    assert env.filters[-1] is None and env.proc.stdin.closed and env.audio.closed
    assert env.logs[-1] == "14:00:05 녹화 종료(프로그램 종료) 20261019_1400_회의.mp4"


def test_kill_when_ffmpeg_does_not_exit(tmp_path):
    env = Env(tmp_path, proc=FakeProc(hang=True))
    env.rec.start(consent())
    env.rec.stop()
    assert env.proc.killed


def test_overlay_error_stops_recording(tmp_path):
    env = Env(tmp_path)
    env.rec.start(consent())
    env.rec.on_overlay_error(RuntimeError("font"))
    assert not env.rec.recording and env.rec.warning == "녹화: 녹화 중 표시 오류로 종료"


def test_start_refused_without_overlay(tmp_path):
    env = Env(tmp_path)

    def broken(name):
        raise OSError("font")

    env.rec.overlay_factory = broken
    r = env.rec.start(consent())
    assert r.message == "녹화를 시작할 수 없습니다: 녹화 중 표시를 만들 수 없습니다" and env.spawned == []


def test_log_failure_does_not_break_recording(tmp_path):
    env = Env(tmp_path)

    def bad_log(line):
        raise UnicodeEncodeError("cp1252", "녹화", 0, 1, "x")

    env.rec.log = bad_log
    r = env.rec.start(consent())
    assert r.ok and env.rec.recording
    assert env.rec.stop() == r.path and not env.rec.recording


def test_overlay_built_at_start_with_current_site_name(tmp_path):  # I5
    env = Env(tmp_path)
    env.rec.s.site_name = "C대학"
    env.rec.start(consent(site_name="C대학"))
    assert env.names == ["C대학"]


def test_start_refused_when_virtual_camera_not_sending(tmp_path):  # I4
    env = Env(tmp_path)
    env.alive = False
    r = env.rec.start(consent())
    assert r.message == "녹화를 시작할 수 없습니다: 가상 카메라로 영상을 보내지 못하고 있습니다"


def test_auto_stop_when_overlay_not_reaching_zoom(tmp_path):  # I4
    env = Env(tmp_path)
    env.rec.start(consent())
    env.alive = False
    env.rec.tick()
    assert not env.rec.recording and env.rec.warning == "녹화: 녹화 중 표시를 내보낼 수 없어 종료"


def test_mic_gate_opens_only_after_one_second(tmp_path):  # I3
    env = Env(tmp_path, audio=FakeAudio(loop=0.0, mic=1.0), gate=True)
    env.rec.start(consent())
    env.rec.pump_once()
    env.mono = 0.9
    env.rec.pump_once()
    assert set(env.proc.stdin.data) == {0}
    env.mono = 1.05
    env.proc.stdin.data.clear()
    env.rec.pump_once()
    assert max(env.proc.stdin.data) > 0


class BlockingStdin(FakeStdin):
    def __init__(self, proc):
        super().__init__()
        self.proc = proc

    def write(self, b):
        import time
        while not self.proc.killed:      # FFmpeg가 읽지 않아 파이프가 가득 찬 상태
            time.sleep(0.01)
        raise BrokenPipeError()

    def close(self):
        if not self.proc.killed:
            import time
            while not self.proc.killed:  # 실제 버퍼 쓰기 잠금처럼 write가 끝날 때까지 막힘
                time.sleep(0.01)
        self.closed = True


def test_stop_does_not_hang_when_ffmpeg_stops_reading(tmp_path):  # C1
    import time
    proc = FakeProc()
    proc.stdin = BlockingStdin(proc)
    env = Env(tmp_path, proc=proc)
    env.rec.threaded = True
    env.rec.start(consent())
    time.sleep(0.1)
    t0 = time.monotonic()
    env.rec.stop()
    assert env.rec.wait_finalized(10)
    assert proc.killed and time.monotonic() - t0 < 6


def test_new_start_refused_while_previous_is_finalizing(tmp_path):  # I7
    proc = FakeProc(hang=True)
    env = Env(tmp_path, proc=proc)
    env.rec.threaded = True
    env.rec.start(consent())
    env.rec.stop()
    r = env.rec.start(consent())
    assert r.ok is False and r.message == "이전 녹화를 마무리하는 중입니다. 잠시 후 다시 시도해 주세요"
    assert env.rec.wait_finalized(15)
    assert env.rec.start(consent()).ok
