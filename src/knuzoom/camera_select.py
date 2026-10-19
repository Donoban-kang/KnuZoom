"""우리 캠퍼스 판정 카메라 선택: 카메라 이름 목록(Windows DirectShow 순서), 가상 카메라 제외, 저장된 이름으로 찾기.

KnuZoom이 Zoom으로 내보내는 가상 카메라를 판정 입력으로 고르면 자기 출력을 다시 읽게 되므로 목록에서 뺀다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from knuzoom.config import Settings, save_settings

VIRTUAL_CAMERA_KEYWORDS = ("obs virtual camera", "obs-camera", "knuzoom")


def is_virtual(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in VIRTUAL_CAMERA_KEYWORDS)


def list_camera_names() -> list[str]:
    """DirectShow 장치 이름(OpenCV CAP_DSHOW 번호 순서와 같음). Windows가 아니거나 실패하면 빈 목록."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def camera_choices(names: list[str]) -> list[tuple[int, str]]:
    return [(i, n) for i, n in enumerate(names) if not is_virtual(n)]


def resolve_camera_index(s: Settings, names: list[str]) -> int:
    """저장된 카메라 이름 → 그 번호. 없으면 저장된 번호(가상 카메라가 아니면). 그것도 아니면 첫 실제 카메라."""
    if not names:
        return s.camera_index
    if s.camera_name and s.camera_name in names and not is_virtual(s.camera_name):
        return names.index(s.camera_name)
    if 0 <= s.camera_index < len(names) and not is_virtual(names[s.camera_index]):
        return s.camera_index
    choices = camera_choices(names)
    return choices[0][0] if choices else s.camera_index


def camera_label(s: Settings, names: list[str]) -> str:
    i = resolve_camera_index(s, names)
    return names[i] if 0 <= i < len(names) else f"카메라 {i}번"


class CameraControl:
    """화면에서 고른 카메라를 설정에 저장하고, 영상 파이프라인을 다시 열고, 엔진에 알린다."""

    def __init__(self, s: Settings, settings_path: Path, *, reopen: Callable[[], None],
                 camera_changed: Callable[[], None],
                 list_names: Callable[[], list[str]] = list_camera_names) -> None:
        self.s = s
        self.path = settings_path
        self.reopen = reopen
        self.camera_changed = camera_changed
        self.list_names = list_names
        self.names: list[str] = list_names()

    def refresh(self) -> list[tuple[int, str]]:
        self.names = self.list_names()
        return camera_choices(self.names)

    def current_index(self) -> int:
        return resolve_camera_index(self.s, self.names)

    def label(self) -> str:
        return camera_label(self.s, self.names)

    def choose(self, index: int) -> bool:
        if not (0 <= index < len(self.names)) or is_virtual(self.names[index]):
            return False
        self.s.camera_index = index
        self.s.camera_name = self.names[index]
        save_settings(self.s, self.path)
        self.reopen()
        self.camera_changed()
        return True
