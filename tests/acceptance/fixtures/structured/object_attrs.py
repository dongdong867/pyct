"""Custom-object argument target.

Attributes are reached through ``__dict__`` rather than subscripting, so
they exercise the third route-segment kind. The class lives at module
level so instances survive the isolated runner's pickling.
"""

from __future__ import annotations


class Rule:
    """Plain attribute holder used as a target argument."""

    def __init__(self, limit: int = 10, label: str = "x") -> None:
        self.limit = limit
        self.label = label


def classify_rule(rule: Rule) -> str:
    if rule.limit > 100:
        return "high_limit"
    if rule.limit < 0:
        return "negative_limit"
    if rule.label == "strict":
        return "strict_mode"
    return "normal"
