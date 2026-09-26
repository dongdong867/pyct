import threading

from pyct.run.threads import running


def test_a_process_with_one_thread_counts_one() -> None:
    assert running() == 1


def test_a_thread_left_running_counts() -> None:
    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, daemon=True)
    thread.start()
    try:
        assert running() == 2
    finally:
        stop.set()
        thread.join()
