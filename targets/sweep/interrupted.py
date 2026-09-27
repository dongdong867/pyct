"""A sweep fixture: a function with nothing to vary, then one whose every call sleeps a minute.

The sleeping call writes its process id and its parent's to the file SWEEP_PIDS_FILE names,
when set, so a test can see that both are gone after the sweep.
"""

import os
import time


def a_main() -> None:
    return None


def b_wait(n: int) -> None:
    pids = os.environ.get("SWEEP_PIDS_FILE")
    if pids:
        with open(pids, "w") as file:
            file.write(f"{os.getpid()} {os.getppid()}\n")
    time.sleep(60)
