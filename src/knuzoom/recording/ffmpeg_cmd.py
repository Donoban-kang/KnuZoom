"""FFmpeg 녹화 명령 생성과 실행 파일 찾기."""
from __future__ import annotations

import shutil
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
    else:
        video = f"testsrc2=size=1280x720:rate={fps}"
        vf = "format=nv12"
    return [
        ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "lavfi", "-i", video,
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
