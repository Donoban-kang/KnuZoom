"""KnuZoom이 두 개 실행되지 않게 한다(두 개가 같은 마이크를 반대로 조작하는 것을 방지).

같은 이름의 뮤텍스를 설치 프로그램(installer/knuzoom.iss의 AppMutex)도 사용해,
업그레이드·제거 때 KnuZoom이 실행 중이면 먼저 종료하라고 안내한다.
"""
from __future__ import annotations

import sys

MUTEX_NAME = "KnuZoomAppMutex"
_ERROR_ALREADY_EXISTS = 183
_handle = None  # 프로그램이 끝날 때까지 뮤텍스를 붙잡아 둔다


def acquire() -> bool:
    """처음 실행이면 True, 이미 실행 중이면 False. Windows가 아니면 항상 True."""
    global _handle
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    _handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def show_already_running() -> None:
    if sys.platform != "win32":
        return
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, "KnuZoom이 이미 실행 중입니다.\n트레이 아이콘에서 [열기]를 눌러 주세요.",
                                     "KnuZoom", 0x40)
