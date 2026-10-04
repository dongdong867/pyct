# A number made once per value and kept, as sympy keeps its numbers. ``lru_cache`` compares two
# keys only when their hashes match, so a call with a value equal to an earlier one forks on that
# compare, and a call with any other value forks nowhere: the solver does not model the hash.
from functools import lru_cache


@lru_cache
def _made(value: int) -> list[int]:
    return [value]


@lru_cache
def _made_once(value: int) -> list[int]:
    # a second value made, never the first, raises: an input whose value missed the cache
    if _made_once.cache_info().currsize:
        raise ValueError("a second number")
    return [value]


def number(value: int) -> list[int]:
    return _made(value)


def strict_number(value: int) -> list[int]:
    return _made_once(value)
