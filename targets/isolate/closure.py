from collections.abc import Callable


def make() -> Callable[[int], str]:
    """A counter no module attribute names: it lives in the closure make returns."""
    calls = 0

    def count(x: int) -> str:
        nonlocal calls
        calls += 1
        seen = False
        if calls > 1:
            seen = True  # marked: runs only when an earlier call left the count above 0
        if x > 3:
            return f"big {seen}"
        return f"small {seen}"

    return count
