"""Triangle classification by side lengths and angle type.

Category: pure_numeric
Intent: Classify a triangle given three integer side lengths into both a shape
    category (equilateral / isosceles / scalene) and an angle category (right /
    obtuse / acute).  Guard clauses reject degenerate inputs.
Challenge: The function mixes inequality guards with arithmetic comparisons
    (Pythagorean check across all three side orderings), producing ~12 reachable
    branches that require the solver to reason about additive and multiplicative
    integer constraints simultaneously.
"""

from __future__ import annotations


def triangle_classification(a: int, b: int, c: int) -> str:
    """Classify a triangle by its side lengths.

    Returns a compound label ``"<shape>_<angle>"`` such as
    ``"equilateral_acute"`` or ``"scalene_right"``, or a guard-clause
    rejection string for degenerate inputs.
    """
    if a <= 0 or b <= 0 or c <= 0:
        return "invalid_non_positive"

    if a + b <= c or a + c <= b or b + c <= a:
        return "not_a_triangle"

    shape = _classify_shape(a, b, c)
    angle = _classify_angle(a, b, c)
    return f"{shape}_{angle}"


def _classify_shape(a: int, b: int, c: int) -> str:
    if a == b == c:
        return "equilateral"
    if a == b or b == c or a == c:
        return "isosceles"
    return "scalene"


def _classify_angle(a: int, b: int, c: int) -> str:
    sides = sorted([a, b, c])
    sq_sum = sides[0] ** 2 + sides[1] ** 2
    sq_max = sides[2] ** 2

    if sq_sum == sq_max:
        return "right"
    if sq_sum < sq_max:
        return "obtuse"
    return "acute"
