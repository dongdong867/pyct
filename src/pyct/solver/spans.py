"""Membership in a range and the equality of two ranges in SMT-LIB, each as one term.

Python answers either without walking a range. An item is in it when it
lies from the start toward the stop, on the side the step's sign says, and
the step divides its distance from the start. Two ranges are equal when they
have the same length and, past an empty one, the same first element and,
past one element, the same step. The sign is an `ite`, so a tracked step
reads as well as a plain one; a zero step never reaches here, since Python
raises on it where the range is built and the path holds that fork. A range
arrives as its arguments' Int terms, a start and a stop, and a step when the
target wrote one.
"""


def _step(bounds: tuple[str, ...]) -> str:
    """A range's step term: the one written, or 1."""
    return bounds[2] if len(bounds) > 2 else "1"


def within(item: str, bounds: tuple[str, ...]) -> str:
    """``item in range(*bounds)`` on Int terms."""
    start, stop, step = bounds[0], bounds[1], _step(bounds)
    upward = f"(and (<= {start} {item}) (< {item} {stop}))"
    if step == "1":
        return upward
    downward = f"(and (< {stop} {item}) (<= {item} {start}))"
    return f"(and (ite (> {step} 0) {upward} {downward}) (= (mod (- {item} {start}) {step}) 0))"


def without(item: str, bounds: tuple[str, ...]) -> str:
    """``item not in range(*bounds)``: the negation of `within`."""
    return f"(not {within(item, bounds)})"


def _length(bounds: tuple[str, ...]) -> str:
    """``len(range(*bounds))``: the steps from the start that stay short of the stop."""
    start, stop, step = bounds[0], bounds[1], _step(bounds)
    upward = f"(ite (< {start} {stop}) (div (+ (- {stop} {start}) (- {step} 1)) {step}) 0)"
    if step == "1":
        return f"(ite (< {start} {stop}) (- {stop} {start}) 0)"
    downward = f"(ite (> {start} {stop}) (div (- (- {start} {stop}) (+ {step} 1)) (- {step})) 0)"
    return f"(ite (> {step} 0) {upward} {downward})"


def equal(left: tuple[str, ...], right: tuple[str, ...]) -> str:
    """``range(*left) == range(*right)``, as Python compares two ranges."""
    length = _length(left)
    same_first = (
        f"(and (= {left[0]} {right[0]}) (or (= {length} 1) (= {_step(left)} {_step(right)})))"
    )
    return f"(and (= {length} {_length(right)}) (or (= {length} 0) {same_first}))"


def unequal(left: tuple[str, ...], right: tuple[str, ...]) -> str:
    """``range(*left) != range(*right)``: the negation of `equal`."""
    return f"(not {equal(left, right)})"
