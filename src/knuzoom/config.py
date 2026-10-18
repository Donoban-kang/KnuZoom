"""설정 값과 JSON 저장/불러오기."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class Settings:
    camera_index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    analysis_fps: int = 5
    min_face_confidence: float = 0.5
    zoom_h: float = 0.22
    wide_h: float = 0.15
    zoom_max_faces: int = 2
    wide_min_faces: int = 3
    unmute_window_s: float = 1.0
    mute_window_s: float = 1.5
    ratio: float = 0.8
    verify_delay_s: float = 1.0
    camera_lost_frames: int = 15
    calibration_sample_s: float = 2.0
    emergency_hotkey: str = "ctrl+alt+k"
    zoom_window_titles: list[str] = field(default_factory=lambda: ["Zoom Meeting", "Zoom 회의"])
    zoom_label_when_muted: list[str] = field(default_factory=lambda: ["Unmute my audio", "오디오 음소거 해제"])
    zoom_label_when_unmuted: list[str] = field(default_factory=lambda: ["Mute my audio", "오디오 음소거"])


def default_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "KnuZoom" / "settings.json"
    return Path.home() / ".knuzoom" / "settings.json"


def load_settings(path: Path) -> Settings:
    """파일이 없거나 깨졌으면 기본값. 모르는 키는 무시하고 없는 키는 기본값."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    return sanitize_settings(Settings(**{k: v for k, v in data.items() if k in known}))[0]


# 숫자 항목의 허용 범위: (최소, 최대, 최소값 포함 여부)
_RANGES: dict[str, tuple[float, float, bool]] = {
    "camera_index": (0, 99, True),
    "width": (1, 7680, True),
    "height": (1, 4320, True),
    "fps": (1, 120, True),
    "analysis_fps": (1, 30, True),
    "min_face_confidence": (0, 1, False),
    "zoom_h": (0, 1, False),
    "wide_h": (0, 1, False),
    "zoom_max_faces": (1, 50, True),
    "wide_min_faces": (1, 50, True),
    "unmute_window_s": (0, 30, False),
    "mute_window_s": (0, 30, False),
    "ratio": (0, 1, False),
    "verify_delay_s": (0, 10, False),
    "camera_lost_frames": (1, 1000, True),
    "calibration_sample_s": (0, 30, False),
}


def _valid(name: str, value: object, default: object) -> bool:
    if isinstance(default, list):
        return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x for x in value)
    if isinstance(default, str):
        return isinstance(value, str) and bool(value.strip())
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(default, int) and not isinstance(value, int):
        return False
    lo, hi, lo_inclusive = _RANGES[name]
    return (value >= lo if lo_inclusive else value > lo) and value <= hi


def sanitize_settings(s: Settings) -> tuple[Settings, list[str]]:
    """잘못된 값(형식·범위)은 기본값으로 되돌리고, 되돌린 항목 이름을 함께 돌려준다."""
    defaults = Settings()
    values = asdict(s)
    problems: list[str] = []
    for f in fields(Settings):
        default = getattr(defaults, f.name)
        if not _valid(f.name, values[f.name], default):
            values[f.name] = default
            problems.append(f.name)
    if values["wide_h"] >= values["zoom_h"]:
        values["wide_h"], values["zoom_h"] = defaults.wide_h, defaults.zoom_h
        problems.append("wide_h")
    return Settings(**values), problems


def save_settings(s: Settings, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
