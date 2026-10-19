"""다른 스레드(트레이 아이콘 등)에서 Tk 화면 작업을 요청할 때 쓰는 대기열.

Tk는 메인 스레드에서만 다뤄야 하므로, 다른 스레드는 post()로 넣고 메인 스레드의 주기 갱신이 drain()으로 실행한다.
"""
from __future__ import annotations

import queue
from typing import Callable


class MainThreadCalls:
    def __init__(self) -> None:
        self._q: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()

    def post(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def drain(self) -> None:
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                return
            fn()
