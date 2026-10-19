"""녹화 파일 이름·저장 폴더·디스크 공간·보관기간·해시 관리."""
from __future__ import annotations

import hashlib
import re
import shutil
from datetime import date, datetime
from pathlib import Path

from knuzoom.config import Settings

_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
_DELETE_DATE = re.compile(r"삭제 예정일: (\d{4}-\d{2}-\d{2})")
MAX_NAME = 30


def safe_filename(meeting: str, start: datetime) -> str:
    name = _FORBIDDEN.sub("", meeting).strip()[:MAX_NAME].strip() or "회의"
    return f"{start:%Y%m%d_%H%M}_{name}.mp4"


def unique_path(directory: Path, filename: str) -> Path:
    """같은 이름이 있으면 _2, _3…을 붙여 덮어쓰지 않는다."""
    path = Path(directory) / filename
    n = 2
    while path.exists() or record_path(path).exists():
        path = Path(directory) / f"{Path(filename).stem}_{n}{Path(filename).suffix}"
        n += 1
    return path


def record_path(mp4: Path) -> Path:
    return Path(mp4).with_suffix(".txt")


def recording_dir(s: Settings) -> Path:
    return Path(s.recording_dir) if s.recording_dir else Path.home() / "Documents" / "KnuZoom 녹화"


def free_gb(path: Path) -> float:
    p = Path(path)
    while not p.exists() and p != p.parent:  # 아직 없는 폴더는 가장 가까운 상위 폴더 기준
        p = p.parent
    return shutil.disk_usage(p).free / 1024 ** 3


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expired_recordings(directory: Path, today: date) -> list[Path]:
    """동의 기록의 삭제 예정일이 지난 녹화(mp4 경로) 목록. 읽을 수 없는 기록은 건너뛴다."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    found = []
    for txt in sorted(directory.glob("*.txt")):
        try:
            m = _DELETE_DATE.search(txt.read_text(encoding="utf-8"))
            if m and date.fromisoformat(m.group(1)) < today:
                found.append(txt.with_suffix(".mp4"))
        except (OSError, ValueError):
            continue
    return found


def delete_recording(mp4: Path) -> None:
    for p in (Path(mp4), record_path(mp4)):
        if p.exists():
            p.unlink()
