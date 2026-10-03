import os
import subprocess
import sys
import threading

import pytest

from pyct.run import threads
from pyct.run.threads import running

# the modules threads imports for itself, loaded first, then threads, printing what that added
IMPORTS_THREADS = (
    "import __future__, collections.abc, contextlib, functools, importlib, os, struct, sys\n"
    "import threading\n"
    "before = set(sys.modules)\n"
    "import pyct.run.threads\n"
    "print(sorted(name for name in set(sys.modules) - before if name.split('.')[0] != 'pyct'))\n"
)


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


def test_counting_threads_leaves_no_module_of_its_own_in_sys_modules() -> None:
    # what ctypes imports, sysconfig on 3.13 and later, would otherwise hide a target's own
    imported = subprocess.run(
        [sys.executable, "-P", "-c", IMPORTS_THREADS],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert imported.stdout == "[]\n", imported.stdout
