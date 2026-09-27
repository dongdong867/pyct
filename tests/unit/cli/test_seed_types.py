import inspect

import pytest

from pyct.cli import UsageError, check_seed_types
from pyct.run.target import Target


def four_plain_types(s: str, n: int, x: float, b: bool) -> str:
    return f"{s}{n}{x}{b}"


class Point:
    """A class target whose body annotation disagrees with its ``__init__``."""

    n: str

    def __init__(self, n: int) -> None:
        self.value = n


def target_for(fn: object) -> Target:
    """A Target around ``fn``: what the seed-type check reads, ``fn`` and its signature."""
    assert callable(fn)
    return Target(spec="m::f", fn=fn, file="m.py", signature=inspect.signature(fn))


def test_check_seed_types_accepts_a_seed_that_fits_a_class_init() -> None:
    check_seed_types(target_for(Point), {"n": 5})


def test_check_seed_types_raises_one_line_per_contradiction() -> None:
    with pytest.raises(UsageError) as raised:
        check_seed_types(target_for(four_plain_types), {"s": 5, "n": "5", "x": 1, "b": True})

    assert str(raised.value) == 's must be a str, got 5\nn must be an int, got "5"'


def test_check_seed_types_accepts_a_matching_seed() -> None:
    check_seed_types(target_for(four_plain_types), {"s": "a", "n": 1, "x": 1.5, "b": True})


class ReadOnce:
    """A callable whose signature Python can read no more: a read raises.

    The test hands the seed check the signature the loader would have read
    before that, in a Target it builds itself.
    """

    @property
    def __signature__(self) -> inspect.Signature:
        raise RuntimeError("the signature was read a second time")

    def __call__(self, n: int) -> int:
        return n


def test_check_seed_types_reads_the_signature_the_loader_read() -> None:
    read_once = ReadOnce()
    loaded = inspect.Signature(
        [inspect.Parameter("n", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int)]
    )
    target = Target(spec="m::read_once", fn=read_once, file="m.py", signature=loaded)

    with pytest.raises(UsageError, match='n must be an int, got "5"'):
        check_seed_types(target, {"n": "5"})
