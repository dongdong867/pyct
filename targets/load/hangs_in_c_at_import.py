"""A module whose import writes its pid where asked, then runs one C call for minutes."""

import os

path = os.environ.get("PYCT_TEST_PID_FILE")
if path is not None:
    with open(path, "w") as file:
        file.write(str(os.getpid()))
sum(range(10**12))


def f(x: int) -> int:
    return x
