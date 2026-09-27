"""A sweep fixture: a module that imports cleanly the first time and, every later time, in any
process, starts a process and sleeps forever.

It counts its imports in the file SWEEP_IMPORTS_FILE names; with the variable unset it always
imports cleanly. On a later import its process id, its parent's, and the one it started go to
the file SWEEP_PIDS_FILE names, when set, so a test can see that all are gone after the sweep.
"""

import os
import subprocess
import time

imports = os.environ.get("SWEEP_IMPORTS_FILE")
if imports:
    with open(imports, "a+") as file:
        file.seek(0)
        before = file.read()
        file.write("x")
    if before:
        started = subprocess.Popen(["/bin/sleep", "3600"])
        pids = os.environ.get("SWEEP_PIDS_FILE")
        if pids:
            with open(pids, "w") as file:
                file.write(f"{os.getpid()} {os.getppid()} {started.pid}\n")
        while True:
            time.sleep(3600)


def price(n: int) -> int:
    if n > 0:
        return n
    return 0
