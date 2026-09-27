"""A sweep fixture: a module whose __all__ names a private function and leaves a public one out."""

__all__ = ["a", "_b"]


def a(n: int) -> int:
    return n + 1


def _b(n: int) -> int:
    return n - 1


def c(n: int) -> int:
    return n * 2
