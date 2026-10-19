from knuzoom import single_instance
from knuzoom.single_instance import MUTEX_NAME, acquire


def test_mutex_name_matches_installer():
    # 설치 파일(installer/knuzoom.iss)의 AppMutex와 같아야 실행 중 업그레이드를 감지한다.
    from pathlib import Path
    iss = Path("installer/knuzoom.iss").read_text(encoding="utf-8-sig")
    assert f"AppMutex={MUTEX_NAME}" in iss


def test_acquire_is_noop_outside_windows(monkeypatch):
    monkeypatch.setattr(single_instance.sys, "platform", "linux")
    assert acquire() is True
