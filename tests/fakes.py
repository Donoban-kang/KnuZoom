class FakeZoom:
    """ZoomAdapter 가짜 구현. press_toggle은 stuck이 아니면 상태를 뒤집는다."""

    def __init__(self, muted=True, active=True, readable=True, stuck=False):
        self.muted = muted
        self.active = active
        self.readable = readable
        self.stuck = stuck
        self.presses = 0

    def meeting_active(self):
        return self.active

    def read_muted(self):
        return self.muted if self.readable else None

    def press_toggle(self):
        self.presses += 1
        if not self.stuck:
            self.muted = not self.muted
