"""A target with a helper it never calls."""


def classify(x: int) -> str:
    if x < 10:
        return "small"
    return "large"


def never_called(x: int) -> int:
    return x * 2
