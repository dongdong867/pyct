"""Branches driven by str() — witness for ConcolicInt.__str__ symbolic routing.

The ``zero`` arm is only reachable if ``str(x)`` preserves the symbolic
link between ``x`` and ``s``. A failure mode would be Python's built-in
``int.__str__`` firing instead of a concolic override, returning a raw
Python str and stripping the symbolic expression.
"""


def format_number(x: int) -> str:
    s = str(x)
    if s == "0":
        return "zero"
    return "nonzero"
