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
                       cwd=SRC, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
