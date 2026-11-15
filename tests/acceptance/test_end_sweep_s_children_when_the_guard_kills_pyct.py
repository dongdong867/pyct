"""A sweep's pyct process held past the stop's grace, as a lock, a slow host or target code can
hold it: the guard kills it, and the entry's run in flight, with every process of that run, is
gone by the time the process the shell started exits."""

import os
import signal
import subprocess
from contextlib import suppress
from pathlib import Path

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
