"""A module that notes each import of itself, one pid a line, in the file PYCT_TEST_IMPORTS names."""

import os

_NOTES = os.environ.get("PYCT_TEST_IMPORTS")
if _NOTES:
    with open(_NOTES, "a") as notes:
        notes.write(f"{os.getpid()}\n")


def f(x: int) -> int:
    if x > 3:
        return 1
    return 0
