"""FFmpeg 녹화 명령 생성과 실행 파일 찾기."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from knuzoom.recording.audio_mix import CHANNELS, SAMPLE_RATE


def build_command(ffmpeg: str, out: Path, monitor: int, fps: int,
                  source: Literal["screen", "test"] = "screen") -> list[str]:
    """화면(또는 시험 영상) + 표준입력 음성(s16le) → H.264/AAC 조각 mp4.

    -shortest: 표준입력(음성)을 닫으면 FFmpeg가 스스로 파일을 마무리한다.
    """
    if source == "screen":
        video = f"ddagrab=output_idx={monitor}:framerate={fps}:draw_mouse=0"
        vf = "hwdownload,format=bgra,format=nv12"
        # 실제 화면 녹화: 음성 시각을 도착 시각으로 맞춰 시작 시점 어긋남을 줄인다(시험 영상은 실시간이 아니라 제외)
        audio_ts = ["-use_wallclock_as_timestamps", "1"]
    else:
        video = f"testsrc2=size=1280x720:rate={fps}"
        vf = "format=nv12"
        audio_ts = []
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "lavfi", "-i", video,
        *audio_ts,
        "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
        "-map", "0:v", "-map", "1:a",
        "-vf", vf, "-c:v", "h264_mf", "-b:v", "4M",
        "-c:a", "aac", "-b:a", "160k", "-af", "aresample=async=1",
        "-shortest",
        "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
        str(out),
    ]


def find_ffmpeg(app_dir: Path | None = None) -> str | None:
    """설치 폴더의 ffmpeg\\ffmpeg.exe를 먼저, 없으면 PATH에서 찾는다."""
    if app_dir is not None:
        bundled = Path(app_dir) / "ffmpeg" / "ffmpeg.exe"
        if bundled.exists():
            return str(bundled)
    return shutil.which("ffmpeg")


class _Spawner:
    """FFmpeg 실행: 오류 출력은 logs/ffmpeg.log에 덧붙이고, 로그 파일 핸들은 실행 직후 닫는다(자식이 따로 가짐)."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = Path(log_dir)
        self._open = 0

    def __call__(self, cmd: list[str]) -> subprocess.Popen:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._open += 1
        try:
            with open(self.log_dir / "ffmpeg.log", "ab") as err:
                return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err,
                                        creationflags=flags)
        finally:
            self._open -= 1

    def open_handles(self) -> int:
        return self._open


def make_spawn(log_dir: Path) -> _Spawner:
    return _Spawner(log_dir)
