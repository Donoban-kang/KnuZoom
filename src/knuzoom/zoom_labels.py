"""Zoom 회의 창 버튼 이름으로 마이크 상태를 판단한다(플랫폼 독립)."""
from __future__ import annotations

import ntpath


def mute_state_from_labels(names: list[str], when_muted: list[str],
                           when_unmuted: list[str]) -> bool | None:
    """음소거면 True, 해제면 False, 판단할 수 없으면 None.

    버튼 이름이 라벨로 시작하는지 본다("Ask to Unmute" 같은 다른 버튼 오인 방지).
    "오디오 음소거 해제"가 "오디오 음소거"로도 시작하므로 muted 라벨을 먼저 전부 확인한다.
    """
    for name in names:
        if any(name.startswith(label) for label in when_muted):
            return True
    for name in names:
        if any(name.startswith(label) for label in when_unmuted):
            return False
    return None


def is_zoom_exe(path: str | None) -> bool:
    """실행 파일 경로가 Zoom 클라이언트(Zoom.exe)인지 본다. 브라우저 탭 제목 오인 방지."""
    if not path:
        return False
    return ntpath.basename(path).lower() == "zoom.exe"
