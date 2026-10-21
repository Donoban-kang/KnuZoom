"""실행 시작 시 모듈을 불러오는 순서 시험(Windows 전용, 새 파이썬 프로세스에서 확인)."""
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.mark.skipif(sys.platform != "win32", reason="COM 초기화는 Windows에서만 확인")
def test_main_module_imports_without_com_mode_conflict():
    # 다른 모듈이 COM을 먼저 STA로 초기화하면 pywinauto(comtypes)가
    # "스레드 모드가 설정된 후에는 바꿀 수 없습니다"로 실패해 프로그램이 켜지지 않는다.
    r = subprocess.run([sys.executable, "-c", "import knuzoom.__main__"],
                       cwd=SRC, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr


_FROZEN_LIKE = """
import ctypes, threading
# 실행파일(PyInstaller)처럼 우리 코드보다 먼저 주 스레드 COM을 STA로 초기화해 둔다
assert ctypes.windll.ole32.CoInitializeEx(None, 2) in (0, 1)
import knuzoom.__main__
from knuzoom.config import Settings
from knuzoom.zoom_windows import WindowsZoomAdapter
a = WindowsZoomAdapter(Settings())
a._meeting_window()  # 주 스레드(종료 시 음소거)
a.read_muted()
errs = []
def work():  # 작업 스레드(마이크 제어·회의 확인)
    try:
        a._meeting_window()
    except Exception as e:
        errs.append(repr(e))
t = threading.Thread(target=work)
t.start(); t.join()
assert not errs, errs
"""


@pytest.mark.skipif(sys.platform != "win32", reason="COM 초기화는 Windows에서만 확인")
def test_starts_and_reads_zoom_when_com_already_sta():
    r = subprocess.run([sys.executable, "-c", _FROZEN_LIKE],
                       cwd=SRC, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, r.stderr
