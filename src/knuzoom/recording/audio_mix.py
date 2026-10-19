"""녹화 음성: 스피커 루프백(상대 기관)과 회의실 마이크를 섞는다. 마이크는 Zoom 해제 중에만 통과."""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 48000
CHANNELS = 2
BLOCK = 960  # 20ms


class MicGate:
    """열림/닫힘 전환 시 fade 샘플에 걸쳐 이득을 선형으로 바꿔 딸깍 소리를 막는다. 처음엔 닫힘."""

    def __init__(self, fade: int = BLOCK) -> None:
        self.step = 1.0 / fade
        self.gain = 0.0

    def process(self, block: np.ndarray, open_: bool) -> np.ndarray:
        target = 1.0 if open_ else 0.0
        n = len(block)
        if self.gain == target:
            gains = np.full(n, target, np.float32)
        else:
            direction = self.step if target > self.gain else -self.step
            gains = np.clip(self.gain + direction * np.arange(1, n + 1), 0.0, 1.0).astype(np.float32)
            gains = np.minimum(gains, target) if direction > 0 else np.maximum(gains, target)
            self.gain = float(gains[-1])
        return block * gains[:, None]


def mix(loop: np.ndarray | None, mic: np.ndarray | None, frames: int = BLOCK) -> np.ndarray:
    out = np.zeros((frames, CHANNELS), np.float32)
    for src in (loop, mic):
        if src is not None:
            out += src[:frames]
    return np.clip(out, -1.0, 1.0)


def to_s16le(block: np.ndarray) -> bytes:
    return np.round(np.clip(block, -1.0, 1.0) * 32767).astype("<i2").tobytes()
