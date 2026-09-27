"""A target that forks two workers, then waits for every child it has until none is left."""

import os


def f(x: int) -> int:
    for _ in range(2):
        if os.fork() == 0:
            os._exit(0)
    reaped = 0
    while True:
        try:
            os.wait()
        except ChildProcessError:
            return reaped
        reaped += 1
