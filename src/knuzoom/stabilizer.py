"""순간 판정을 모아 안정된 WIDE/ZOOM 상태로 확정한다."""
from __future__ import annotations

from collections import deque

from knuzoom.config import Settings
from knuzoom.detector import Verdict

_EPS = 1e-9


class Stabilizer:
    def __init__(self, s: Settings) -> None:
        self.s = s
        self.state = Verdict.WIDE
        self._hist: deque[tuple[float, Verdict]] = deque()
        self._ref: float | None = None  # 이력 충분 판단 기준 시각

    def reset(self, t: float) -> None:
        self.state = Verdict.WIDE
        self._hist.clear()
        self._ref = None

    def update(self, t: float, v: Verdict) -> Verdict | None:
        """판정 하나를 넣고, 상태가 바뀌면 새 상태를 돌려준다."""
        self._hist.append((t, v))
        if self._ref is None:
            self._ref = t
        keep = max(self.s.unmute_window_s, self.s.mute_window_s)
        while self._hist and self._hist[0][0] < t - keep - _EPS:
            self._hist.popleft()

        if self.state is Verdict.WIDE:
            window, target = self.s.unmute_window_s, Verdict.ZOOM
        else:
            window, target = self.s.mute_window_s, Verdict.WIDE
        if self._ref > t - window + _EPS:
            return None  # 이력 부족

        recent = [x for (ts, x) in self._hist if ts > t - window + _EPS]
        if recent and sum(x is target for x in recent) / len(recent) >= self.s.ratio - _EPS:
            self.state = target
            self._ref = t
            return target
        return None
