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


def test_sanitize_resets_wrong_type_to_default():  # M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(zoom_h="abc", camera_index=True))
    assert s.zoom_h == 0.22 and s.camera_index == 0
    assert "zoom_h" in problems and "camera_index" in problems


def test_sanitize_resets_out_of_range():  # M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(unmute_window_s=0, ratio=1.5, analysis_fps=0))
    assert (s.unmute_window_s, s.ratio, s.analysis_fps) == (1.0, 0.8, 5)
    assert set(problems) >= {"unmute_window_s", "ratio", "analysis_fps"}


def test_sanitize_requires_wide_below_zoom():  # M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(wide_h=0.3, zoom_h=0.2))
    assert (s.wide_h, s.zoom_h) == (0.15, 0.22) and "wide_h" in problems


def test_sanitize_rejects_empty_or_non_string_lists():  # M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(zoom_window_titles=[], zoom_label_when_muted="Unmute"))
    assert s.zoom_window_titles == ["Zoom Meeting", "Zoom 회의"]
    assert s.zoom_label_when_muted == ["Unmute my audio", "오디오 음소거 해제"]


def test_sanitize_keeps_valid_settings():  # M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(zoom_h=0.3, wide_h=0.1))
    assert problems == [] and (s.wide_h, s.zoom_h) == (0.1, 0.3)


def test_load_applies_sanitize(tmp_path):  # M4
    p = tmp_path / "s.json"
    p.write_text('{"mute_window_s": -1, "zoom_h": "x"}', encoding="utf-8")
    s = load_settings(p)
    assert s.mute_window_s == 1.5 and s.zoom_h == 0.22


def test_int_value_for_float_field_becomes_float():  # 재검토 M4
    from knuzoom.config import sanitize_settings
    s, problems = sanitize_settings(Settings(mute_window_s=2))
    assert problems == [] and isinstance(s.mute_window_s, float) and s.mute_window_s == 2.0


def test_wide_h_reported_once():  # 재검토 M4
    from knuzoom.config import sanitize_settings
    _, problems = sanitize_settings(Settings(wide_h="x", zoom_h=0.1))
    assert problems.count("wide_h") == 1


def test_load_reports_reset_fields(tmp_path):  # 재검토 M4
    from knuzoom.config import load_settings_with_problems
    p = tmp_path / "s.json"
    p.write_text('{"ratio": 5}', encoding="utf-8")
    s, problems = load_settings_with_problems(p)
    assert s.ratio == 0.8 and problems == ["ratio"]
