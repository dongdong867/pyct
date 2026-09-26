"""A target wrapped by a decorator defined in another module."""

from targets.compare.decorator import logged


@logged
def classify(x: int) -> str:
    if x < 10:
        return "small"
    return "large"
