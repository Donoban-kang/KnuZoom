"""Windows의 Zoom Workplace를 UI Automation과 Alt+A로 제어한다(Windows 전용)."""
from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes

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

# 실행파일(PyInstaller)은 우리 코드보다 먼저 주 스레드의 COM을 STA로 초기화해 둔다. 주 스레드에서
# pywinauto를 불러오면 MTA로 바꾸려다 "스레드 모드가 설정된 후에는 바꿀 수 없습니다"로 실패하고,
# STA 객체를 다른 스레드에서 쓰면 주 스레드가 기다리는 동안 서로 멈출 수 있다.
# 그래서 UI Automation은 전용 스레드(MTA) 하나에서만 불러오고 실행한다.
_ole32 = ctypes.WinDLL("ole32")


def _init_uia_thread() -> None:
    _ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED


_uia = ThreadPoolExecutor(max_workers=1, thread_name_prefix="knuzoom-uia", initializer=_init_uia_thread)


def _on_uia_thread(fn):
    """fn을 UI Automation 전용 스레드에서 실행하고 결과를 돌려준다(예외도 그대로 전달)."""
    return _uia.submit(fn).result()


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
        return _on_uia_thread(self._find_meeting_window)

    def _find_meeting_window(self):
        from pywinauto import Desktop  # 전용 스레드에서 처음 불러오도록 여기서 불러온다
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
        def labels():
            w = self._find_meeting_window()
            return None if w is None else [b.window_text() for b in w.descendants(control_type="Button")]
        try:
            names = _on_uia_thread(labels)
            if names is None:
                return None
        except Exception:
            return None
        return mute_state_from_labels(names, self.s.zoom_label_when_muted,
                                      self.s.zoom_label_when_unmuted)

    def press_toggle(self) -> None:
        # Zoom 설정에서 Alt+A "전역 단축키"를 켜 두어야 Zoom 창이 앞에 없어도 동작한다.
        # 긴급 정지(Ctrl+Alt+K) 직후 Ctrl·Shift·Win이 눌린 채로 남아 있으면 Zoom이 Alt+A로 인식하지 못하므로 먼저 뗀다.
        def press():
            from pywinauto.keyboard import send_keys
            send_keys("{VK_CONTROL up}{VK_SHIFT up}{VK_LWIN up}{VK_RWIN up}%a")
        _on_uia_thread(press)
