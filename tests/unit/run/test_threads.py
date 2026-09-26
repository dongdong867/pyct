import os
import sys
import threading

import pytest

from pyct.run import threads
from pyct.run.threads import running


def test_a_thread_left_running_counts_once() -> None:
    before = running()
    stop = threading.Event()
    thread = threading.Thread(target=stop.wait, daemon=True)
    thread.start()
    try:
        assert running() == before + 1
    finally:
        stop.set()
        thread.join()


def test_the_main_thread_counts() -> None:
    assert running() >= 1


def test_where_the_system_gives_no_count_python_s_count_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a platform with no count pyct reads: Python's own is all there is
    monkeypatch.setattr(sys, "platform", "sunos5")

    assert running() == threading.active_count()


def test_a_task_directory_that_cannot_be_read_leaves_python_s_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(path: str) -> list[str]:
        raise FileNotFoundError(2, "No such file or directory", path)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "listdir", refuse)

    assert running() == threading.active_count()


@pytest.mark.skipif(sys.platform != "darwin", reason="the task's thread count is macOS's")
def test_a_task_count_the_system_will_not_give_leaves_python_s_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # a flavor proc_pidinfo does not know writes nothing back
    monkeypatch.setattr(threads, "_TASK_INFO", 999)

    assert running() == threading.active_count()
