import threading

from knuzoom.ui_calls import MainThreadCalls


def test_calls_posted_from_other_thread_run_only_on_drain_in_order():  # M1
    calls, out = MainThreadCalls(), []
    t = threading.Thread(target=lambda: [calls.post(lambda i=i: out.append(i)) for i in range(3)])
    t.start(); t.join()
    assert out == []
    calls.drain()
    assert out == [0, 1, 2]
    calls.drain()
    assert out == [0, 1, 2]
