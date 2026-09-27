"""A sweep fixture: a module that starts a process and sleeps forever while it is imported.

Its own process id and the one it started go to the file SWEEP_PIDS_FILE names, when set,
so a test can see that both are gone after the sweep.
"""

import os
import subprocess
import time

started = subprocess.Popen(["/bin/sleep", "3600"])
pids = os.environ.get("SWEEP_PIDS_FILE")
if pids:
    with open(pids, "w") as file:
        file.write(f"{os.getpid()} {started.pid}\n")
while True:
    time.sleep(3600)
