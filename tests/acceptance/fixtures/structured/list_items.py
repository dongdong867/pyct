"""List-argument target.

``items[0] == items[1]`` is the discriminating branch: today every list
element shares one symbolic name, so that comparison collapses to a
tautology and the constraint the solver receives describes a single
scalar rather than two independent elements. Per-index naming is what
makes the two elements distinguishable.
"""

from __future__ import annotations


def classify_pair(items: list) -> str:
    if items[0] > 100:
        return "first_large"
    if items[1] < -50:
        return "second_negative"
    if items[0] == items[1]:
        return "equal_elements"
    return "other"
