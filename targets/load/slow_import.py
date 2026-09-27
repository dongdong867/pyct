"""A module whose import takes long, then ends its process; it writes its pid where asked first."""

import os
import time

path = os.environ.get("PYCT_TEST_PID_FILE")
if path is not None:
    with open(path, "w") as file:
        file.write(str(os.getpid()))
time.sleep(30)
os._exit(3)


def f(x: int) -> int:
    return x
