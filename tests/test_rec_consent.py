from datetime import datetime

from knuzoom.recording.consent import ConsentRecord, notice_text, render_text, validate


def rec(**kw):
    base = dict(meeting="○○협의회", site_name="B대학", required_parties=["A대학", "C대학", "D대학"],
                agreed_parties=["A대학", "C대학", "D대학"], method="사전 공문", method_other="",
                purpose="회의록 작성", retention_days=30)
    return ConsentRecord(**{**base, **kw})


def test_valid_record():
    assert validate(rec()) == []


def test_missing_party_blocks():
    assert validate(rec(agreed_parties=["A대학"])) == ["동의하지 않은 기관이 있습니다: C대학, D대학"]


def test_blank_meeting_and_purpose():
    assert "회의명을 입력해 주세요" in validate(rec(meeting="  "))
    assert "녹화 목적을 입력해 주세요" in validate(rec(purpose=""))


def test_method_required():
    assert validate(rec(method="")) == ["동의 방법을 선택해 주세요"]


def test_other_method_needs_text():
    assert validate(rec(method="기타")) == ["기타 동의 방법을 적어 주세요"]


def test_retention_range():
    assert validate(rec(retention_days=0)) == ["보관기간은 1~3650일이어야 합니다"]


def test_render_text_while_recording():
    t = render_text(rec(), datetime(2026, 10, 19, 14, 0, 5), "20261019_1400_○○협의회.mp4")
    assert "회의명: ○○협의회" in t and "녹화 기관: B대학" in t
    assert "동의 기관: A대학, C대학, D대학" in t and "동의 방법: 사전 공문" in t
    assert "보관기간: 30일 (삭제 예정일: 2026-11-18)" in t
    assert "녹화 시작: 2026-10-19 14:00:05" in t
    assert "녹화 종료: (녹화 중)" in t and "SHA-256: (종료 시 계산)" in t


def test_render_text_other_method():
    t = render_text(rec(method="기타", method_other="이메일"), datetime(2026, 10, 19), "f.mp4")
    assert "동의 방법: 기타(이메일)" in t


def test_render_text_finished():
    t = render_text(rec(), datetime(2026, 10, 19, 14, 0, 5), "f.mp4", datetime(2026, 10, 19, 15, 12, 40), "ab12")
    assert "녹화 종료: 2026-10-19 15:12:40" in t and "SHA-256: ab12" in t


def test_notice_text():
    assert notice_text(rec()) == "[안내] B대학에서 이 회의를 녹화하고 있습니다. (목적: 회의록 작성, 보관: 30일)"
