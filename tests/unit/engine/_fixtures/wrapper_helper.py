"""Helper module for scope-regression fixtures.

The wrapper target (wrapper_target.py) delegates all logic here. When
exploration uses a narrow scope bound to the wrapper's file, these
helper branches never count toward ``is_fully_covered``, and the
engine terminates at iter=1 as soon as the wrapper's single return
statement is covered.
"""

from __future__ import annotations


def classify(s: str) -> str:
    if len(s) > 5:
        return "long"
    if s.startswith("a"):
        return "starts_a"
    if s.endswith("z"):
        return "ends_z"
    return "other"
