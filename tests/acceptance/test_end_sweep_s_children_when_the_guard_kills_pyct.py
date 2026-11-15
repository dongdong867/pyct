"""A sweep's pyct process held past the stop's grace, as a lock, a slow host or target code can
hold it: the guard kills it, and the lister or the entry's run in flight, with every process of
it, is gone by the time the process the shell started exits."""

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT
from tests.acceptance.sweeping import FIXTURES, SWEEP, environment
from tests.acceptance.test_run_a_package_s_entries import interrupted_sweep
from tests.acceptance.test_run_a_target_in_a_throwaway_process import is_running
from tests.acceptance.test_the_watcher import group_ended, parent_of


def children_of(pid: int) -> list[int]:
    """The pids of the processes whose parent is ``pid``, as ``ps`` tells them."""
    told = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, check=True)
    pairs = (line.split() for line in told.stdout.splitlines())
    return [int(child) for child, parent in pairs if int(parent) == pid]


# end-sweep-s-children-when-the-guard-kills-pyct
def test_a_sigterm_ends_the_entry_run_of_a_sweep_held_past_the_grace(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    with interrupted_sweep(pids) as process:
        input_pid, runs_it = (int(pid) for pid in pids.read_text().split())
        # the entry's pyct run: the process sweep started, which leads a group of its own
        entry = parent_of(runs_it)
        # its pyct process and its guard, and the input its pyct process runs
        under = [entry, *children_of(entry), input_pid]
        try:
            os.kill(parent_of(entry), signal.SIGSTOP)
            os.kill(process.pid, signal.SIGTERM)
            process.wait(timeout=10)

            assert process.returncode == -signal.SIGTERM
            assert group_ended(entry)
            assert not [pid for pid in under if is_running(pid)]
        finally:
            # macOS refuses a group whose only member has exited unreaped
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(entry, signal.SIGKILL)


@contextmanager
def stalled_lister(pids: Path) -> Iterator[subprocess.Popen[bytes]]:
    """``pyct sweep --list`` on the stall fixture, in a session of its own, once the module that
    hangs in the lister's import has written its pid and its child's to ``pids``. Nothing it
    names outlives the test."""
    process = subprocess.Popen(
        [*SWEEP, f"{FIXTURES}.stall", "--list"],
        cwd=REPO_ROOT,
        env=environment({"SWEEP_PIDS_FILE": str(pids)}),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not (pids.exists() and pids.read_text().endswith("\n")):
            assert time.monotonic() < deadline, "the hanging import never started"
            time.sleep(0.05)
        yield process
    finally:
        # the lister leads the group of its own that the first pid names; macOS refuses a group
        # whose only member has exited unreaped
        lister = pids.read_text().split()[:1] if pids.exists() else []
        for group in (process.pid, *(int(pid) for pid in lister)):
            with suppress(ProcessLookupError, PermissionError):
                os.killpg(group, signal.SIGKILL)
        process.wait()


# end-sweep-s-children-when-the-guard-kills-pyct: the lister, held in an import that hangs
def test_a_sigterm_ends_the_lister_of_a_sweep_held_past_the_grace(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    with stalled_lister(pids) as process:
        # the lister, the process sweep started, which leads a group of its own, and its child
        lister, started = (int(pid) for pid in pids.read_text().split())
        os.kill(parent_of(lister), signal.SIGSTOP)
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)

        assert process.returncode == -signal.SIGTERM
        assert group_ended(lister)
        assert not [pid for pid in (lister, started) if is_running(pid)]
