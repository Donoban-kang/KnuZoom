from knuzoom.config import Settings, load_settings, save_settings


def test_defaults_match_spec():
    s = Settings()
    assert (s.zoom_h, s.wide_h, s.zoom_max_faces, s.wide_min_faces) == (0.22, 0.15, 2, 3)
    assert (s.unmute_window_s, s.mute_window_s, s.ratio) == (1.0, 1.5, 0.8)
    assert s.analysis_fps == 5 and s.verify_delay_s == 1.0
    assert s.emergency_hotkey == "ctrl+alt+k"


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = Settings(zoom_h=0.3)
    save_settings(s, p)
    assert load_settings(p) == s


def test_missing_file_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "none.json") == Settings()


def test_unknown_and_missing_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"zoom_h": 0.3, "obsolete": 1}', encoding="utf-8")
    s = load_settings(p)
    assert s.zoom_h == 0.3 and s.wide_h == 0.15


def test_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_settings(p) == Settings()
