"""What a signal sent to pyct does, now that pyct's work runs in a process of its own.

The process the shell started watches that process, so these tests send their signals to
the pid the shell got, as a person or a harness does, and check that the run and its input's
process end as they did when that pid was pyct's own.
"""

import os
import signal
import time
from pathlib import Path

from tests.acceptance.test_run_a_target_in_a_throwaway_process import (
    is_running,
    pid_written_to,
    pyct_in_a_session,
)

C_HANG = "targets.isolate.c_hang::stall"
# how soon after the signal every process of the run must have ended
ENDED_WITHIN = 1.5


def group_ended(group: int) -> bool:
    """Whether no process of ``group`` is left, after a moment for the system to reap them."""
    for _ in range(20):
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


# a SIGTERM ends the run, and the input's process with it, as a Ctrl-C does
def test_a_sigterm_ends_the_run_and_its_input(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    with pyct_in_a_session(C_HANG, pid_file) as process:
        child = pid_written_to(pid_file, process)
        sent = time.monotonic()
        os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
        took = time.monotonic() - sent

        assert process.returncode == -signal.SIGTERM
        assert took < ENDED_WITHIN, took
        assert not is_running(child)
        assert group_ended(process.pid)
