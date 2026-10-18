from knuzoom.config import Settings
from knuzoom.detector import FaceStats, Verdict, classify

S = Settings()


def test_zoom():
    assert classify(FaceStats(1, 0.30), S) is Verdict.ZOOM


def test_zoom_boundary():
    assert classify(FaceStats(2, 0.22), S) is Verdict.ZOOM


def test_three_faces_wide():
    assert classify(FaceStats(3, 0.30), S) is Verdict.WIDE


def test_small_faces_wide():
    assert classify(FaceStats(5, 0.10), S) is Verdict.WIDE


def test_wide_boundary():
    assert classify(FaceStats(1, 0.15), S) is Verdict.WIDE


def test_between_uncertain():
    assert classify(FaceStats(1, 0.18), S) is Verdict.UNCERTAIN


def test_no_face_is_uncertain():  # Review Focus 1
    assert classify(FaceStats(0, 0.0), S) is Verdict.UNCERTAIN


def test_uses_settings():
    assert classify(FaceStats(1, 0.18), Settings(zoom_h=0.17)) is Verdict.ZOOM
