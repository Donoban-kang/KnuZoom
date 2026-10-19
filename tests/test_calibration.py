import pytest

from knuzoom.calibration import compute_thresholds, median_h


def test_formula():
    w, z = compute_thresholds(0.10, 0.30)
    assert w == pytest.approx(0.16) and z == pytest.approx(0.24)


def test_zoom_not_larger_returns_none():
    assert compute_thresholds(0.30, 0.30) is None
    assert compute_thresholds(0.30, 0.20) is None


def test_missing_returns_none():
    assert compute_thresholds(None, 0.3) is None
    assert compute_thresholds(0.1, None) is None


def test_median():
    assert median_h([0.1, 0.5, 0.2]) == 0.2
    assert median_h([]) is None


def test_tiny_gap_returns_none():  # M5
    assert compute_thresholds(0.20, 0.22) is None
