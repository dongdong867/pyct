"""A target whose every input takes a while, and notes its start in the file PYCT_TEST_INPUTS names."""

import os
import time

# how many values of x the target tells apart, one fork each
VALUES = 30


def f(x: int) -> int:
    _note()
    time.sleep(0.2)
    for n in range(VALUES):
        if x == n:
            return n
    return -1


def _note() -> None:
    path = os.environ.get("PYCT_TEST_INPUTS")
    if path is not None:
        with open(path, "a") as notes:
            notes.write(f"{os.getpid()}\n")
