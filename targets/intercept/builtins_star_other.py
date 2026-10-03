import builtins
from os.path import *


def check(s: str) -> str:
    if builtins.len(s) > 3:
        return "long"
    return "short"
