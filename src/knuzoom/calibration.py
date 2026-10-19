"""넓은 장면/확대 장면 표본으로 판정 기준값을 계산한다."""
from __future__ import annotations

import statistics

# 넓은 장면과 확대 장면의 H 차이가 이보다 작으면 판정 간격(히스테리시스)이 거의 없어 보정을 거부한다.
MIN_GAP = 0.05


def median_h(samples: list[float]) -> float | None:
    return statistics.median(samples) if samples else None


def compute_thresholds(h_wide: float | None, h_zoom: float | None) -> tuple[float, float] | None:
    """(wide_h, zoom_h)를 돌려준다. 계산할 수 없으면 None."""
    if h_wide is None or h_zoom is None or h_zoom - h_wide < MIN_GAP:
        return None
    d = h_zoom - h_wide
    return h_wide + d * 0.3, h_wide + d * 0.7
