"""A module that raises ``KeyboardInterrupt`` while it is imported, as a Ctrl-C would."""

raise KeyboardInterrupt


def f(x: int) -> int:
    return x
