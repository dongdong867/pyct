"""A module that writes the import path it sees, as JSON, to the file PYCT_TEST_PATH names.

Only its first import writes, so the file holds the path of the process that imported it first.
"""

import json
import os
import sys

_TOLD = os.environ.get("PYCT_TEST_PATH")
if _TOLD is not None:
    try:
        with open(_TOLD, "x") as told:
            json.dump(sys.path, told)
    except FileExistsError:
        pass


def f(x: int) -> int:
    if x > 3:
        return 1
    return 0
