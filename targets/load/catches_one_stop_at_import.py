"""A module whose import writes its pid where asked, catches one BaseException, then finishes."""

import os
import time

path = os.environ.get("PYCT_TEST_PID_FILE")
if path is not None:
    with open(path, "w") as file:
        file.write(str(os.getpid()))
caught = False
while not caught:
    try:
        time.sleep(0.05)
    except BaseException:
        caught = True


def f(x: int) -> int:
    if x > 3:
        return 1
    return 0
