"""Windows CI 녹화 시험: 시험 영상(testsrc2) + 440Hz 사인파 5초를 실제 FFmpeg로 mp4 녹화하고 길이를 확인한다.

사용: python scripts/record_smoke.py <ffmpeg.exe 경로>   (같은 폴더의 ffprobe.exe로 길이 확인)
"""
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from knuzoom.config import Settings
from knuzoom.recording.audio_mix import BLOCK, SAMPLE_RATE
from knuzoom.recording.consent import ConsentRecord
from knuzoom.recording.recorder import Recorder

SECONDS = 5


class SineAudio:
    def __init__(self):
        self.n = 0

    def read(self, frames):
        t = (np.arange(frames) + self.n) / SAMPLE_RATE
        self.n += frames
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        return np.stack([tone, tone], axis=1), None

    def close(self):
        pass


def main() -> int:
    ffmpeg = sys.argv[1]
    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    out_dir = Path(tempfile.mkdtemp())
    rec = Recorder(
        Settings(recording_dir=str(out_dir), min_free_gb_start=0.1, min_free_gb_stop=0.05),
        ffmpeg=ffmpeg,
        spawn=lambda cmd: subprocess.Popen(cmd, stdin=subprocess.PIPE),
        open_audio=SineAudio, gate_open=lambda: False, meeting_active=lambda: True,
        set_filter=lambda f: None, log=print, overlay=lambda f: f, source="test", threaded=False)
    consent = ConsentRecord("CI 녹화 시험", "B대학", ["A대학"], ["A대학"], "사전 공문", "", "시험", 1)
    result = rec.start(consent)
    if not result.ok:
        print("start failed:", result.message)
        return 1
    for _ in range(SECONDS * SAMPLE_RATE // BLOCK):
        rec.pump_once()
    path = rec.stop("시험 종료")
    print(path.with_suffix(".txt").read_text(encoding="utf-8"))
    duration = float(subprocess.check_output(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True).strip())
    print(f"mp4: {path.name} size={path.stat().st_size} bytes duration={duration:.2f}s warning={rec.warning}")
    return 0 if duration >= SECONDS - 1 else 1


if __name__ == "__main__":
    sys.exit(main())
