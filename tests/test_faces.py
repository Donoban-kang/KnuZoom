from pathlib import Path

import numpy as np
import pytest

from knuzoom.detector import FaceStats
from knuzoom.faces import FaceAnalyzer

SAMPLE = Path("tests/data/closeup.jpg")


def test_blank_frame_has_no_faces():
    a = FaceAnalyzer(0.5)
    assert a.analyze(np.zeros((720, 1280, 3), np.uint8)) == FaceStats(0, 0.0)
    a.close()


@pytest.mark.skipif(not SAMPLE.exists(), reason="동의받은 샘플 이미지 필요")
def test_sample_closeup_is_large():
    import cv2
    st = FaceAnalyzer(0.5).analyze(cv2.imread(str(SAMPLE)))
    assert st.n >= 1 and st.h >= 0.22
