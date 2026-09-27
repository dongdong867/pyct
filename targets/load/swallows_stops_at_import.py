"""A module whose import writes its pid where asked, then loops, catching every BaseException."""

import os
import time

path = os.environ.get("PYCT_TEST_PID_FILE")
if path is not None:
    with open(path, "w") as file:
        file.write(str(os.getpid()))
while True:
    try:
        time.sleep(0.05)
    except BaseException:
        pass


def f(x: int) -> int:
    return x
