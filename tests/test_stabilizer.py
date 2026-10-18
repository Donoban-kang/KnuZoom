from knuzoom.config import Settings
from knuzoom.detector import Verdict
from knuzoom.stabilizer import Stabilizer


def feed(st, seq, t0=0.0, dt=0.2):
    out = []
    for i, v in enumerate(seq):
        r = st.update(round(t0 + i * dt, 6), v)
        if r is not None:
            out.append(r)
    return out


def test_starts_wide():
    assert Stabilizer(Settings()).state is Verdict.WIDE


def test_needs_full_window_of_history():  # Review Focus 2
    st = Stabilizer(Settings())
    assert st.update(0.0, Verdict.ZOOM) is None
    assert st.update(0.2, Verdict.ZOOM) is None
    assert st.state is Verdict.WIDE


def test_unmute_after_one_second_of_zoom():
    st = Stabilizer(Settings())
    out = feed(st, [Verdict.ZOOM] * 6)  # t=0.0..1.0
    assert out[-1] is Verdict.ZOOM and st.state is Verdict.ZOOM


def test_brief_zoom_does_not_unmute():
    st = Stabilizer(Settings())
    feed(st, [Verdict.WIDE] * 10)
    feed(st, [Verdict.ZOOM] * 3 + [Verdict.WIDE] * 5, t0=2.0)
    assert st.state is Verdict.WIDE


def test_uncertain_counts_against():
    st = Stabilizer(Settings())
    feed(st, [Verdict.ZOOM, Verdict.UNCERTAIN] * 10)
    assert st.state is Verdict.WIDE


def test_mute_needs_one_and_half_seconds():
    st = Stabilizer(Settings())
    feed(st, [Verdict.ZOOM] * 6)            # → ZOOM at t=1.0
    feed(st, [Verdict.WIDE] * 7, t0=1.2)    # t=1.2..2.4 (1.2s) → 유지
    assert st.state is Verdict.ZOOM
    feed(st, [Verdict.WIDE] * 2, t0=2.6)    # t=2.6에서 (1.1, 2.6] 창 충족
    assert st.state is Verdict.WIDE


def test_face_lost_while_zoomed_keeps_unmuted():
    st = Stabilizer(Settings())
    feed(st, [Verdict.ZOOM] * 6)
    feed(st, [Verdict.UNCERTAIN] * 50, t0=1.2)
    assert st.state is Verdict.ZOOM


def test_reset():
    st = Stabilizer(Settings())
    feed(st, [Verdict.ZOOM] * 6)
    st.reset(5.0)
    assert st.state is Verdict.WIDE
    assert st.update(5.2, Verdict.ZOOM) is None
