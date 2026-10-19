"""가상 카메라 영상 우상단에 "● 녹화 중 (기관명)"을 합성한다(다른 참석 기관이 볼 수 있게)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_SIZE = 28
PAD = 12
MARGIN = 16
_WINDOWS_FONT = r"C:\Windows\Fonts\malgun.ttf"


def _font(font_path: str | None):
    for p in (font_path, _WINDOWS_FONT):
        if p and Path(p).exists():
            return ImageFont.truetype(p, FONT_SIZE)
    try:
        return ImageFont.load_default(size=FONT_SIZE)
    except TypeError:  # 오래된 Pillow
        return ImageFont.load_default()


class RecordingOverlay:
    def __init__(self, site_name: str, font_path: str | None = None) -> None:
        font = _font(font_path)
        text = f"녹화 중 ({site_name})"
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        left, top, right, bottom = probe.textbbox((0, 0), text, font=font)
        dot = FONT_SIZE - 8
        w = PAD + dot + PAD // 2 + (right - left) + PAD
        h = max(FONT_SIZE, bottom - top) + 2 * PAD
        img = Image.new("RGBA", (w, h), (0, 0, 0, 160))
        d = ImageDraw.Draw(img)
        cy = h // 2
        d.ellipse((PAD, cy - dot // 2, PAD + dot, cy + dot // 2), fill=(220, 40, 40, 255))
        d.text((PAD + dot + PAD // 2 - left, (h - (bottom - top)) // 2 - top), text, font=font,
               fill=(255, 255, 255, 255))
        rgba = np.asarray(img, dtype=np.float32)
        self._bgr = rgba[..., [2, 1, 0]]
        self._alpha = rgba[..., 3:4] / 255.0

    def apply(self, frame_bgr: np.ndarray) -> np.ndarray:
        out = frame_bgr.copy()
        fh, fw = out.shape[:2]
        oh, ow = self._alpha.shape[:2]
        x0, y0 = fw - MARGIN - ow, MARGIN
        # 프레임이 표시보다 작으면 겹치는 부분만 합성
        sx, sy = max(0, -x0), 0
        x0, y0 = max(0, x0), min(y0, fh)
        h, w = min(oh - sy, fh - y0), min(ow - sx, fw - x0)
        if h <= 0 or w <= 0:
            return out
        a = self._alpha[sy:sy + h, sx:sx + w]
        region = out[y0:y0 + h, x0:x0 + w].astype(np.float32)
        out[y0:y0 + h, x0:x0 + w] = (self._bgr[sy:sy + h, sx:sx + w] * a + region * (1 - a)).astype(np.uint8)
        return out
