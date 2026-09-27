"""Membership in a range in SMT-LIB: ``x in range(start, stop, step)`` as one term.

Python answers it without walking the range: the item lies from the start
toward the stop, on the side the step's sign says, and the step divides its
distance from the start. The sign is an `ite`, so a tracked step reads as
well as a plain one; a zero step never reaches here, since Python raises on
it where the range is built and the path holds that fork.
"""


def within(item: str, bounds: tuple[str, ...]) -> str:
    """``item in range(*bounds)`` on Int terms: a start and a stop, and a step when written."""
    start, stop, *stepped = bounds
    upward = f"(and (<= {start} {item}) (< {item} {stop}))"
    if not stepped or stepped[0] == "1":
        return upward
    step = stepped[0]
    downward = f"(and (< {stop} {item}) (<= {item} {start}))"
    return f"(and (ite (> {step} 0) {upward} {downward}) (= (mod (- {item} {start}) {step}) 0))"


def without(item: str, bounds: tuple[str, ...]) -> str:
    """``item not in range(*bounds)``: the negation of `within`."""
    return f"(not {within(item, bounds)})"
