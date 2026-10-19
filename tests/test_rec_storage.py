from datetime import date, datetime
from pathlib import Path

from knuzoom.config import Settings
from knuzoom.recording.storage import (delete_recording, expired_recordings, free_gb, record_path,
                                       recording_dir, safe_filename, sha256_file, unique_path)

T = datetime(2026, 10, 19, 14, 0)


def test_filename():
    assert safe_filename("○○ 협의회", T) == "20261019_1400_○○ 협의회.mp4"


def test_filename_strips_forbidden():
    assert safe_filename('a/b:c*?"<>|', T) == "20261019_1400_abc.mp4"


def test_filename_truncates():
    assert safe_filename("가" * 40, T) == "20261019_1400_" + "가" * 30 + ".mp4"


def test_filename_fallback_when_name_empty():  # RF1
    assert safe_filename(' /:* ', T) == "20261019_1400_회의.mp4"


def test_unique_path_adds_suffix(tmp_path):  # RF2
    (tmp_path / "x.mp4").write_bytes(b"1")
    (tmp_path / "x_2.mp4").write_bytes(b"1")
    assert unique_path(tmp_path, "x.mp4") == tmp_path / "x_3.mp4"


def test_unique_path_free_name(tmp_path):
    assert unique_path(tmp_path, "x.mp4") == tmp_path / "x.mp4"


def test_record_path():
    assert record_path(Path("d/a.mp4")) == Path("d/a.txt")


def test_recording_dir_default_and_custom(tmp_path):
    assert recording_dir(Settings()) == Path.home() / "Documents" / "KnuZoom 녹화"
    assert recording_dir(Settings(recording_dir=str(tmp_path))) == tmp_path


def test_expired_recordings(tmp_path):
    for name, d in [("old", "2026-10-01"), ("new", "2026-12-01")]:
        (tmp_path / f"{name}.mp4").write_bytes(b"v")
        (tmp_path / f"{name}.txt").write_text(f"보관기간: 30일 (삭제 예정일: {d})", encoding="utf-8")
    (tmp_path / "bad.txt").write_text("엉망", encoding="utf-8")
    assert expired_recordings(tmp_path, date(2026, 10, 19)) == [tmp_path / "old.mp4"]


def test_expired_recordings_missing_dir(tmp_path):
    assert expired_recordings(tmp_path / "없음", date(2026, 10, 19)) == []


def test_delete_recording(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"v")
    (tmp_path / "a.txt").write_text("t", encoding="utf-8")
    delete_recording(tmp_path / "a.mp4")
    assert list(tmp_path.iterdir()) == []


def test_sha256(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_free_gb_for_missing_dir(tmp_path):
    assert free_gb(tmp_path / "없음" / "더없음") > 0


def test_filename_strips_control_characters():  # 경미 5
    assert safe_filename("회의\t1\n차\x00", T) == "20261019_1400_회의1차.mp4"


def test_finalize_orphans_marks_unfinished_records(tmp_path):  # 경미 3
    from knuzoom.recording.storage import finalize_orphans
    (tmp_path / "a.mp4").write_bytes(b"abc")
    (tmp_path / "a.txt").write_text("녹화 종료: (녹화 중)\nSHA-256: (종료 시 계산)\n", encoding="utf-8")
    (tmp_path / "b.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("녹화 종료: 2026-10-19 15:00:00\nSHA-256: 1234\n", encoding="utf-8")
    fixed = finalize_orphans(tmp_path, datetime(2026, 10, 20, 9, 0, 0))
    assert fixed == [tmp_path / "a.mp4"]
    t = (tmp_path / "a.txt").read_text(encoding="utf-8")
    assert "녹화 종료: (비정상 종료 — 2026-10-20 09:00:00 다음 실행 때 확인)" in t
    assert "SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" in t
    assert "SHA-256: 1234" in (tmp_path / "b.txt").read_text(encoding="utf-8")


def test_finalize_orphans_skips_active_path(tmp_path):
    from knuzoom.recording.storage import finalize_orphans
    (tmp_path / "a.mp4").write_bytes(b"abc")
    (tmp_path / "a.txt").write_text("SHA-256: (종료 시 계산)\n", encoding="utf-8")
    assert finalize_orphans(tmp_path, datetime(2026, 10, 20), skip=tmp_path / "a.mp4") == []
