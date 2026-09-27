"""A module that reads memory at address zero while it is imported, which crashes."""

import ctypes

ctypes.string_at(0)


def f(x: int) -> int:
    return x
