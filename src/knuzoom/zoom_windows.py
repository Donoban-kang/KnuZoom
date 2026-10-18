"""Windows의 Zoom Workplace를 UI Automation과 Alt+A로 제어한다(Windows 전용)."""
from __future__ import annotations

from pywinauto import Desktop
from pywinauto.keyboard import send_keys

from knuzoom.config import Settings
from knuzoom.zoom_labels import mute_state_from_labels


class WindowsZoomAdapter:
    def __init__(self, s: Settings) -> None:
        self.s = s

    def _meeting_window(self):
        for w in Desktop(backend="uia").windows():
            try:
                title = w.window_text()
            except Exception:
                continue
            if any(t in title for t in self.s.zoom_window_titles):
                return w
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
        send_keys("%a")
