import struct
import time

import pytest

from pyct.branches.compare import Parts, compare, same_expression
from pyct.core.foundation.branch import Branch, Expression, Site


def fork(line: int, *, taken: bool) -> Branch:
    """A fork on x at its own line, so the forks of a path are told apart."""
    return Branch(
        expression=["<", "x", line], taken=taken, site=Site(file="m.py", line=line, col=7)
    )


def test_a_path_that_is_the_plan_followed_it() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))

    assert compare(planned, planned) is None


def test_a_path_may_go_on_past_the_plan() -> None:
    planned = (fork(2, taken=True),)
    actual = (fork(2, taken=True), fork(3, taken=False))

    assert compare(planned, actual) is None


def test_a_fork_the_plan_wanted_that_never_happened_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(2, taken=True),)

    assert compare(planned, actual) == 1


def test_a_fork_taken_the_other_way_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(2, taken=True), fork(3, taken=True))

    assert compare(planned, actual) == 1


def test_a_fork_at_another_site_is_the_mismatch() -> None:
    planned = (fork(2, taken=True), fork(3, taken=False))
    actual = (fork(9, taken=True), fork(3, taken=False))

    assert compare(planned, actual) == 0


def chain(depth: int) -> Expression:
    """A sum one term longer on each pass, as `total = total + items[i]` builds one."""
    built: Expression = "total"
    for at in range(depth):
        built = ["+", built, ["[]", "items", at]]
    return built


def rebuilt(passes: int) -> Expression:
    """A string rebuilt from pieces of itself on each pass: each holds the last one three
    times, as one shared list."""
    built: Expression = "s"
    for at in range(passes):
        built = [
            "+",
            ["+", ["[:]", built, None, at], ["[]", built, at]],
            ["[:]", built, at + 1, None],
        ]
    return ["==", built, "'abc'"]


def nan_of(bits: int) -> float:
    """The float whose bits are ``bits``."""
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def test_two_expressions_built_apart_with_the_same_parts_are_the_same() -> None:
    one: Expression = [
        "and",
        ["==", ["float", "s"], 1e-30],
        ["<", ["len", "s"], 3],
        ["is", "x", None],
    ]
    other: Expression = [
        "and",
        ["==", ["float", "s"], 1e-30],
        ["<", ["len", "s"], 3],
        ["is", "x", None],
    ]

    assert same_expression(one, other, Parts(100)) is True


@pytest.mark.parametrize(
    ("one", "other"),
    [
        (["==", "n", 1], ["==", "n", 1.0]),
        (["==", "n", 1], ["==", "n", True]),
        (["==", "n", 1.0], ["==", "n", True]),
        (["==", "s", "1"], ["==", "s", 1]),
        (["==", "x", 0.0], ["==", "x", -0.0]),
        (["==", "x", nan_of(0x7FF8000000000000)], ["==", "x", nan_of(0x7FF8000000000001)]),
        (["==", "x", None], ["==", "x", "None"]),
        (["<", "x", 1], ["<", "x", 1, 2]),
        (["<", "x", 1], ["<", ["x"], 1]),
        (["<", "x", 1], ["<", "y", 1]),
    ],
)
def test_expressions_that_differ_in_a_literal_s_type_bits_or_shape_are_not_the_same(
    one: Expression, other: Expression
) -> None:
    assert same_expression(one, other, Parts(100)) is False


def test_a_nan_is_the_same_as_a_nan_of_the_same_bits() -> None:
    one: Expression = ["==", "x", nan_of(0x7FF8000000000000)]
    other: Expression = ["==", "x", nan_of(0x7FF8000000000000)]

    assert same_expression(one, other, Parts(100)) is True


def test_a_chain_ten_thousand_deep_is_compared_without_recursion() -> None:
    assert same_expression(chain(10_000), chain(10_000), Parts(100_000)) is True
    assert same_expression(chain(10_000), chain(10_001), Parts(100_000)) is False


def test_an_expression_whose_parts_are_shared_compares_each_shared_part_once() -> None:
    started = time.monotonic()

    same = same_expression(rebuilt(40), rebuilt(40), Parts(100_000))

    assert same is True
    assert time.monotonic() - started < 1.0


def test_a_comparison_past_its_parts_cannot_tell() -> None:
    assert same_expression(chain(10), chain(10), Parts(5)) is None


def test_the_parts_one_comparison_spent_are_gone_for_the_next() -> None:
    parts = Parts(40)

    assert same_expression(chain(5), chain(5), parts) is True
    assert same_expression(chain(5), chain(5), parts) is None
