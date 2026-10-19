from knuzoom.tray_state import tray_appearance


def test_tray_normal_and_recording():  # 경미 7
    assert tray_appearance(False) == ("#1f9d55", "KnuZoom")
    assert tray_appearance(True) == ("#d64545", "KnuZoom — ● 녹화 중")
