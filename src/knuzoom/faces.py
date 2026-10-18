"""MediaPipe 얼굴 검출로 프레임에서 FaceStats를 구한다. 얼굴을 식별하지 않으며 저장하지 않는다."""
from __future__ import annotations

import cv2
import mediapipe as mp
import numpy as np

from knuzoom.detector import FaceStats


class FaceAnalyzer:
    def __init__(self, min_confidence: float) -> None:
        # model_selection=1: 원거리(약 5m) 모델. 회의실 거리에 맞춘다.
        self._det = mp.solutions.face_detection.FaceDetection(
            model_selection=1, min_detection_confidence=min_confidence)

    def analyze(self, frame_bgr: np.ndarray) -> FaceStats:
        res = self._det.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        dets = res.detections or []
        if not dets:
            return FaceStats(0, 0.0)
        h = max(d.location_data.relative_bounding_box.height for d in dets)
        return FaceStats(len(dets), min(max(float(h), 0.0), 1.0))

    def close(self) -> None:
        self._det.close()
