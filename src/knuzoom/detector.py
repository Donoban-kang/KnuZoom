"""한 장면의 얼굴 통계로 WIDE / ZOOM / 불확실을 판정한다."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from knuzoom.config import Settings


@dataclass(frozen=True)
class FaceStats:
    n: int    # 검출된 얼굴 수
    h: float  # 가장 큰 얼굴 높이 / 화면 높이


class Verdict(Enum):
    WIDE = "WIDE"
    ZOOM = "ZOOM"
    UNCERTAIN = "UNCERTAIN"


def classify(stats: FaceStats, s: Settings) -> Verdict:
    # 얼굴이 없으면 H=0이 WIDE 기준에 걸리므로 먼저 불확실로 처리한다.
    if stats.n == 0:
        return Verdict.UNCERTAIN
    if stats.h >= s.zoom_h and stats.n <= s.zoom_max_faces:
        return Verdict.ZOOM
    if stats.h <= s.wide_h or stats.n >= s.wide_min_faces:
        return Verdict.WIDE
    return Verdict.UNCERTAIN
