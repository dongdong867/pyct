"""A module whose import forks two workers, then waits for every child it has until none is left."""

import os

for _ in range(2):
    if os.fork() == 0:
        os._exit(0)
while True:
    try:
        os.wait()
    except ChildProcessError:
        break


def f(x: int) -> int:
    return x
