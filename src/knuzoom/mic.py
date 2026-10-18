"""Zoom 마이크를 원하는 상태로 맞추는 제어기."""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable, Protocol


MAX_PRESSES = 2
SETTLE_EXTRA_READS = 2
SETTLE_POLL_S = 0.3


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
        # 작업 스레드(apply)와 UI 스레드(sync_estimate)가 추정값을 함께 고치므로 잠근다.
        self._lock = threading.Lock()
        self.press_count = 0  # Alt+A를 보낸 횟수. [상태 맞추기] 답이 낡았는지 판단하는 데 쓴다.

    def sync_estimate(self, muted: bool, since: int | None = None) -> bool:
        """진행자가 알려준 실제 상태로 추정을 고친다.

        since는 진행자에게 물어본 시점의 press_count. 그 뒤 Alt+A를 보냈다면 답이 낡았으므로 반영하지 않고 False.
        """
        with self._lock:
            if since is not None and since != self.press_count:
                return False
            self.estimated_muted = muted
            return True

    def _press(self) -> None:
        self.press_count += 1
        self.adapter.press_toggle()

    def apply(self, want_muted: bool) -> ApplyResult:
        with self._lock:
            return self._apply_locked(want_muted)

    def _apply_locked(self, want_muted: bool) -> ApplyResult:
        if not self.adapter.meeting_active():
            return ApplyResult.NO_MEETING
        first = self.adapter.read_muted()
        if first is None:
            # 예비 모드: 마지막으로 보낸 명령으로 상태를 추정한다.
            if self.estimated_muted != want_muted:
                self._press()
                self.estimated_muted = want_muted
            return ApplyResult.ESTIMATED
        # Alt+A는 토글이므로 확인된 상태가 원하는 상태와 다를 때만 누른다(최초 1회 + 재시도 1회).
        cur: bool | None = first
        for attempt in range(MAX_PRESSES + 1):
            if cur is None:
                # 상태를 모르면 더 누르지 않는다. 확인된 반대 상태에서 눌렀으므로 원하는 상태로 추정한다.
                self.estimated_muted = want_muted
                return ApplyResult.ESTIMATED
            if cur == want_muted:
                self.estimated_muted = want_muted
                return ApplyResult.OK
            if attempt == MAX_PRESSES:
                break
            before = cur
            self._press()
            cur = self._settle(before)
        return ApplyResult.FAILED if want_muted else ApplyResult.BLOCKED

    def _settle(self, before: bool) -> bool | None:
        """누른 뒤 Zoom 버튼 문구가 늦게 바뀔 수 있으므로, 바뀔 때까지 몇 번 더 읽는다."""
        self.sleep(self.verify_delay_s)
        cur = self.adapter.read_muted()
        for _ in range(SETTLE_EXTRA_READS):
            if cur != before:
                break
            self.sleep(SETTLE_POLL_S)
            cur = self.adapter.read_muted()
        return cur
