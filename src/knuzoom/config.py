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
    zoom_label_when_muted: list[str] = field(default_factory=lambda: ["Unmute", "음소거 해제"])
    zoom_label_when_unmuted: list[str] = field(default_factory=lambda: ["Mute", "음소거"])


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
    return Settings(**{k: v for k, v in data.items() if k in known})


def save_settings(s: Settings, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2), encoding="utf-8")
