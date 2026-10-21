"""Windows의 Zoom Workplace를 UI Automation과 Alt+A로 제어한다(Windows 전용)."""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

# 실행파일(PyInstaller)은 우리 코드보다 먼저 주 스레드의 COM을 STA로 초기화해 둔다.
# pywinauto는 지정이 없으면 MTA로 초기화하려다 "스레드 모드가 설정된 후에는 바꿀 수 없습니다"로 실패하므로
# 주 스레드는 STA로 맞춘다(일반 실행도 같게). 작업 스레드는 _ensure_com()에서 각자 초기화한다.
if not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED

from pywinauto import Desktop  # noqa: E402
from pywinauto.keyboard import send_keys  # noqa: E402

from knuzoom.config import Settings
from knuzoom.zoom_labels import is_zoom_exe, mute_state_from_labels

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 다른 라이브러리와 공유하는 ctypes.windll.kernel32를 건드리지 않도록 별도로 불러와 형식을 지정한다(64비트 HANDLE).
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                             ctypes.POINTER(wintypes.DWORD))
_k32.CloseHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)

_ole32 = ctypes.WinDLL("ole32")
_com = threading.local()


def _ensure_com() -> None:
    """이 스레드에서 처음 UI Automation을 쓰기 전에 COM을 초기화한다(스레드마다 한 번)."""
    if getattr(_com, "ready", False):
        return
    _ole32.CoInitializeEx(None, 0)  # MTA. 주 스레드처럼 이미 초기화된 스레드는 실패 코드만 돌려주고 그대로 둔다
    _com.ready = True


def _exe_path(pid: int) -> str | None:
    """프로세스 번호로 실행 파일 전체 경로를 얻는다(실패하면 None)."""
    k32 = _k32
    h = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return None
        return buf.value
    finally:
        k32.CloseHandle(h)


class WindowsZoomAdapter:
    def __init__(self, s: Settings) -> None:
        self.s = s

    def _meeting_window(self):
        _ensure_com()
        for w in Desktop(backend="uia").windows():
            try:
                title = w.window_text()
            except Exception:
                continue
            if not any(t in title for t in self.s.zoom_window_titles):
                continue
            try:
                if is_zoom_exe(_exe_path(w.element_info.process_id)):  # 같은 제목의 브라우저 탭 등 제외
                    return w
            except Exception:
                continue
        return None

    def meeting_active(self) -> bool:
        try:
            return self._meeting_window() is not None
        except Exception:
            return False

    def read_muted(self) -> bool | None:
        try:
            w = self._meeting_window()
            if w is None:
                return None
            names = [b.window_text() for b in w.descendants(control_type="Button")]
        except Exception:
            return None
        return mute_state_from_labels(names, self.s.zoom_label_when_muted,
                                      self.s.zoom_label_when_unmuted)

    def press_toggle(self) -> None:
        # Zoom 설정에서 Alt+A "전역 단축키"를 켜 두어야 Zoom 창이 앞에 없어도 동작한다.
        # 긴급 정지(Ctrl+Alt+K) 직후 Ctrl·Shift·Win이 눌린 채로 남아 있으면 Zoom이 Alt+A로 인식하지 못하므로 먼저 뗀다.
        send_keys("{VK_CONTROL up}{VK_SHIFT up}{VK_LWIN up}{VK_RWIN up}%a")
