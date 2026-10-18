"""Zoom 회의 창 버튼 이름으로 마이크 상태를 판단한다(플랫폼 독립)."""
from __future__ import annotations


def mute_state_from_labels(names: list[str], when_muted: list[str],
                           when_unmuted: list[str]) -> bool | None:
    """음소거면 True, 해제면 False, 판단할 수 없으면 None.

    "Unmute"/"음소거 해제"가 "Mute"/"음소거"를 포함하므로 muted 라벨을 먼저 전부 확인한다.
    """
    for name in names:
        if any(label in name for label in when_muted):
            return True
    for name in names:
        if any(label in name for label in when_unmuted):
            return False
    return None
