import os
import subprocess
import sys
import threading

import pytest

from pyct.run import threads
from pyct.run.threads import running
from tests.acceptance.harness import COVERAGE_STARTUP

# threads imported and asked for a count, printing what ctypes, which reads the count on macOS,
# left in sys.modules: itself, its C half, or the sysconfig it imports on 3.13 and later
COUNTS_THREADS = (
    "import sys\n"
    "before = set(sys.modules)\n"
    "from pyct.run.threads import running\n"
    "assert running() >= 1\n"
    "added = set(sys.modules) - before\n"
    "kept = {'ctypes', '_ctypes', 'sysconfig'}\n"
    "print(sorted(n for n in added if n in kept or n.startswith(('ctypes.', 'sysconfig.'))))\n"
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


def test_counting_threads_leaves_neither_ctypes_nor_sysconfig_in_sys_modules() -> None:
    # what ctypes imports, sysconfig on 3.13 and later, would otherwise hide a target's own;
    # coverage.py's start-up would import sysconfig first, so the child runs unmeasured
    unmeasured = {k: v for k, v in os.environ.items() if k not in COVERAGE_STARTUP}
    imported = subprocess.run(
        [sys.executable, "-P", "-c", COUNTS_THREADS],
        env=unmeasured,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert imported.stdout == "[]\n", imported.stdout
