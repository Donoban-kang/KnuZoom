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
