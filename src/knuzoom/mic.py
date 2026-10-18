"""Zoom 마이크를 원하는 상태로 맞추는 제어기."""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable, Protocol


class ZoomAdapter(Protocol):
    def meeting_active(self) -> bool: ...
    def read_muted(self) -> bool | None: ...  # 읽을 수 없으면 None
    def press_toggle(self) -> None: ...


class ApplyResult(Enum):
    OK = "OK"
    NO_MEETING = "NO_MEETING"
    BLOCKED = "BLOCKED"      # 해제를 원했지만 재시도 후에도 음소거
    FAILED = "FAILED"        # 음소거를 원했지만 재시도 후에도 해제
    ESTIMATED = "ESTIMATED"  # 상태를 읽을 수 없어 추정으로 적용


class MicController:
    def __init__(self, adapter: ZoomAdapter, verify_delay_s: float,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.adapter = adapter
        self.verify_delay_s = verify_delay_s
        self.sleep = sleep
        self.estimated_muted = True

    def sync_estimate(self, muted: bool) -> None:
        self.estimated_muted = muted

    def apply(self, want_muted: bool) -> ApplyResult:
        if not self.adapter.meeting_active():
            return ApplyResult.NO_MEETING
        if self.adapter.read_muted() is None:
            # 예비 모드: 마지막으로 보낸 명령으로 상태를 추정한다.
            if self.estimated_muted != want_muted:
                self.adapter.press_toggle()
                self.estimated_muted = want_muted
            return ApplyResult.ESTIMATED
        # Alt+A는 토글이므로 다를 때만 누르고, 누를 때마다 결과를 다시 확인한다(최초 1회 + 재시도 1회).
        for _attempt in range(2):
            if self.adapter.read_muted() == want_muted:
                break
            self.adapter.press_toggle()
            self.sleep(self.verify_delay_s)
        if self.adapter.read_muted() == want_muted:
            self.estimated_muted = want_muted
            return ApplyResult.OK
        return ApplyResult.FAILED if want_muted else ApplyResult.BLOCKED
