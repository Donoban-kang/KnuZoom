"""Windows의 Zoom Workplace를 UI Automation과 Alt+A로 제어한다(Windows 전용)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

from knuzoom.config import Settings
from knuzoom.zoom_labels import is_zoom_exe, mute_state_from_labels

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _exe_path(pid: int) -> str | None:
    """프로세스 번호로 실행 파일 전체 경로를 얻는다(실패하면 None)."""
    k32 = ctypes.windll.kernel32
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
        # 긴급 정지(Ctrl+Alt+K) 직후 Ctrl·Shift가 눌린 채로 남아 있으면 Zoom이 Alt+A로 인식하지 못하므로 먼저 뗀다.
        send_keys("{VK_CONTROL up}{VK_SHIFT up}%a")
