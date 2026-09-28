"""How deep a value this Python nests before one of its recursive readers or writers refuses it.

JSON's reader and writer and pickle recurse once per level. Up to 3.13 CPython stops them at a
count of levels; from 3.14 it stops them when the stack runs low, so the depth differs between
releases and machines. A test reads it here, in its own process, instead of writing one down.
"""

from collections.abc import Callable


def refuses(call: Callable[[int], object], depth: int) -> bool:
    """Whether the call on a value nested this deep raises RecursionError."""
    try:
        call(depth)
    except RecursionError:
        return True
    return False


def refused_depth(call: Callable[[int], object]) -> int:
    """The smallest depth at which the call raises RecursionError in this process.

    Each depth past it is refused too, since the call recurses once per level.
    """
    low, high = 1, 1024
    while not refuses(call, high):
        low, high = high + 1, high * 2
    while low < high:
        middle = (low + high) // 2
        if refuses(call, middle):
            high = middle
        else:
            low = middle + 1
    return low


def nested_list(depth: int) -> list[object]:
    """A list holding a list, and so on ``depth`` lists deep, the innermost holding 0."""
    value: list[object] = [0]
    for _ in range(depth - 1):
        value = [value]
    return value


def nested_dict(depth: int) -> dict[str, object]:
    """A dict whose one value is a dict, and so on ``depth`` dicts deep, the innermost's 0."""
    value: dict[str, object] = {"a": 0}
    for _ in range(depth - 1):
        value = {"a": value}
    return value


def nested_text(depth: int) -> str:
    """`nested_dict` as JSON text: an object nesting ``depth`` objects deep, its own among them."""
    return '{"a": ' * depth + "0" + "}" * depth
