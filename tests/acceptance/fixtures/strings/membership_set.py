"""Literal-container membership branch target.

The branch ``x in {"red", "green", "blue"}`` requires the engine to
synthesize an input whose value matches one of the three literal
container elements. The seed value ``"none"`` matches no element, so
the engine must flip the membership disjuncts to produce inputs that
exercise each element of the container individually.

This anchors the ``membership-per-element-branches`` AC: the engine
should produce at least one input matching each of the three string
elements within 2 * N (= 6) iterations, with each matching iteration
flipping a distinct path-condition disjunct.
"""


def matches_color(x: str) -> str:
    if x in {"red", "green", "blue"}:
        return "match"
    return "nomatch"
