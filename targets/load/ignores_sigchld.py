"""A module that sets SIGCHLD to be ignored at import, so every blocking wait waits for all children."""

import signal

signal.signal(signal.SIGCHLD, signal.SIG_IGN)


def f(x: int) -> int:
    return x
