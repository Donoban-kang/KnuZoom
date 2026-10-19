"""트레이 아이콘 모양: 녹화 중이면 빨간색과 '● 녹화 중' 제목."""
from __future__ import annotations

GREEN, RED = "#1f9d55", "#d64545"


def tray_appearance(recording: bool) -> tuple[str, str]:
    return (RED, "KnuZoom — ● 녹화 중") if recording else (GREEN, "KnuZoom")
