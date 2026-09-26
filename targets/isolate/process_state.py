import os
import sys

# far from any limit Python starts with, so only an earlier call could have set it
LIMIT = 4321


def disturb(x: int) -> str:
    found = []
    if "PYCT_DISTURBED" in os.environ:
        found.append("environment")  # marked
    if os.getcwd() == os.path.abspath(os.sep):
        found.append("directory")  # marked
    if sys.getrecursionlimit() == LIMIT:
        found.append("recursion limit")  # marked
    os.environ["PYCT_DISTURBED"] = "1"
    os.chdir(os.sep)
    sys.setrecursionlimit(LIMIT)
    if x > 3:
        return "big"
    return "small"
