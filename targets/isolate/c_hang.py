import os

# about ten seconds of adding inside one C call that never returns to Python on the way
TERMS = 1_600_000_000


def stall(x: int) -> str:
    if x > 3:
        _tell_pid()
        return str(sum(range(TERMS)))  # hangs in C
    return "quick"


def _tell_pid() -> None:
    """Write this process's pid where a test asked for it, so the test can look for it later."""
    path = os.environ.get("PYCT_TEST_PID_FILE")
    if path is not None:
        with open(path, "w") as file:
            file.write(str(os.getpid()))
