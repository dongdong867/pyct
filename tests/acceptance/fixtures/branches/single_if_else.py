"""Single if/else target — minimal branching."""


def classify(x: int) -> str:
    if x > 0:
        return "positive"
    return "non_positive"
