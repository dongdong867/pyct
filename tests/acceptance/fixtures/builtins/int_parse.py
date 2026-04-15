"""Branches driven by int() — witness for ConcolicStr.__int__ symbolic routing.

The ``zero`` arm is only reachable if the engine can synthesize a string
that parses to 0 under symbolic constraints. A failure mode would be
``ConcolicStr.__int__`` returning a raw Python int, stripping the
symbolic link between ``s`` and ``n``.
"""


def parse_number(s: str) -> str:
    try:
        n = int(s)
    except ValueError:
        return "invalid"
    if n == 0:
        return "zero"
    return "nonzero"
