from fakes import FakeZoom
from knuzoom.mic import ApplyResult, MicController


def nosleep(_):
    pass


def test_no_press_when_already_in_state():
    z = FakeZoom(muted=True); c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(True) is ApplyResult.OK and z.presses == 0


def test_unmute_presses_once_and_verifies():
    z = FakeZoom(muted=True); slept = []
    c = MicController(z, 1.0, sleep=slept.append)
    assert c.apply(False) is ApplyResult.OK
    assert z.presses == 1 and z.muted is False and slept == [1.0]


def test_host_block_reports_blocked_after_one_retry():
    z = FakeZoom(muted=True, stuck=True); c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(False) is ApplyResult.BLOCKED and z.presses == 2


def test_mute_failure_reports_failed():
    z = FakeZoom(muted=False, stuck=True); c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(True) is ApplyResult.FAILED


def test_no_meeting():
    z = FakeZoom(active=False); c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(False) is ApplyResult.NO_MEETING and z.presses == 0


def test_estimated_mode_presses_only_on_change():
    z = FakeZoom(muted=True, readable=False); c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(True) is ApplyResult.ESTIMATED and z.presses == 0
    assert c.apply(False) is ApplyResult.ESTIMATED and z.presses == 1
    assert c.apply(False) is ApplyResult.ESTIMATED and z.presses == 1


def test_sync_estimate():
    z = FakeZoom(muted=False, readable=False); c = MicController(z, 1.0, sleep=nosleep)
    c.sync_estimate(False)
    assert c.apply(False) is ApplyResult.ESTIMATED and z.presses == 0


def test_unknown_read_during_retry_never_presses_blind():  # Final I1
    from fakes import ScriptedZoom
    z = ScriptedZoom([False, None, None, None], muted=False, stuck=True)
    c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(True) is ApplyResult.ESTIMATED and z.presses == 1


def test_late_label_update_does_not_double_toggle():  # Final I2
    from fakes import ScriptedZoom
    z = ScriptedZoom([False, False, False], muted=False)   # 누른 뒤 두 번은 옛 상태를 보여줌
    c = MicController(z, 1.0, sleep=nosleep)
    assert c.apply(True) is ApplyResult.OK and z.presses == 1 and z.muted is True


def test_sync_estimate_waits_for_running_apply():  # M7
    import threading
    started, release = threading.Event(), threading.Event()

    class BlockingZoom(FakeZoom):
        def press_toggle(self):
            started.set(); release.wait(2)
            super().press_toggle()

    z = BlockingZoom(muted=True, readable=False)
    c = MicController(z, 0.0, sleep=nosleep)
    t = threading.Thread(target=c.apply, args=(False,)); t.start()
    started.wait(2)
    done = threading.Event()
    threading.Thread(target=lambda: (c.sync_estimate(True), done.set())).start()
    assert not done.wait(0.2)          # apply가 끝날 때까지 기다려야 함
    release.set(); t.join(2)
    assert done.wait(2) and c.estimated_muted is True
