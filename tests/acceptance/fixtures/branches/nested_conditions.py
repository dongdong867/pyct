"""Nested if/else target — tests path combinations (2x2 = 4 distinct paths)."""


def categorize(x: int, y: int) -> str:
    if x > 0:
        if y > 0:
            return "both_positive"
        return "x_positive_only"
    if y > 0:
        return "y_positive_only"
    return "neither"
