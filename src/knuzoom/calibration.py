"""넓은 장면/확대 장면 표본으로 판정 기준값을 계산한다."""
from __future__ import annotations

import statistics


def median_h(samples: list[float]) -> float | None:
    return statistics.median(samples) if samples else None


def compute_thresholds(h_wide: float | None, h_zoom: float | None) -> tuple[float, float] | None:
    """(wide_h, zoom_h)를 돌려준다. 계산할 수 없으면 None."""
    if h_wide is None or h_zoom is None or h_zoom <= h_wide:
        return None
    d = h_zoom - h_wide
    return h_wide + d * 0.3, h_wide + d * 0.7
