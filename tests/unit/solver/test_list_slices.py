"""Positions and slices of a tracked list as terms: bounds read as sums, and clamps settled the
way the input whose path this is went."""

import pytest

from pyct.core.branch import Expression
from pyct.solver.list_kinds import Kinds, access
from pyct.solver.list_slices import Slices
from pyct.solver.list_terms import Lin, Shown, ite, nested

N = "|arg.items.len|"
INDEX = "|arg.i|"
NONE = Kinds(frozenset(), frozenset())


def slices(*, settle: bool = False, n: int = 3, i: int = 1) -> Slices:
    """Slices of a list the input held ``n`` items of, with a tracked ``i`` it held as ``i``."""
    made = Slices()
    made.named = lambda part: INDEX if part == "i" else "e!7"
    made.least[N] = 0
    made.origin.update({N: n, INDEX: i})
    made.settle = settle
    return made


def base() -> Shown:
    return Shown(Lin.of(N), frozenset(), frozenset())


@pytest.mark.parametrize(
    ("bound", "sum_"),
    [
        (["+", "i", 1], Lin(1, ((INDEX, 1),))),
        (["-", "i", 2], Lin(-2, ((INDEX, 1),))),
        (["-", "i"], Lin(0, ((INDEX, -1),))),
        (["*", 3, "i"], Lin(0, ((INDEX, 3),))),
        (["*", "i", "i"], None),
        (["//", "i", 2], None),
    ],
)
def test_a_bound_that_sums_leaves_and_numbers_is_read_as_the_sum(
    bound: Expression, sum_: Lin | None
) -> None:
    made = slices(settle=False)

    read = made._bound(bound)

    assert read == (sum_ if sum_ is not None else Lin.of("e!7"))
    # the answer reads the bound's value whichever way it is written
    assert id(bound) in made.positions


def test_a_bound_nested_too_deep_is_a_term_of_its_own() -> None:
    deep: Expression = "i"
    for _ in range(10):
        deep = ["+", deep, 1]

    assert slices(settle=False)._bound(deep) == Lin.of("e!7")


@pytest.mark.parametrize(
    ("bounds", "start", "length", "held"),
    [
        # the input held 3 items: 1 is inside, 5 past the end, -1 counts back, -5 before
        ([1, None], Lin(1), Lin(-1, ((N, 1),)), ["(assert (<= 1 |arg.items.len|))"]),
        ([5, None], Lin.of(N), Lin(), ["(assert (not (<= 5 |arg.items.len|)))"]),
        ([-1, None], Lin(-1, ((N, 1),)), Lin(1), ["(assert (<= 0 (+ |arg.items.len| (- 1))))"]),
        ([-5, None], Lin(), Lin.of(N), ["(assert (not (<= 0 (+ |arg.items.len| (- 5)))))"]),
    ],
)
def test_a_clamp_the_path_leaves_open_goes_the_way_the_input_went(
    bounds: list[Expression], start: Lin, length: Lin, held: list[str]
) -> None:
    made = slices()

    window = made.window(base(), bounds, NONE, settle=True)

    assert (window.start, window.length) == (start, length)
    assert list(made.regime) == held


@pytest.mark.parametrize(
    ("bounds", "start"),
    [
        ([1, None, -1], Lin(1)),
        ([5, None, -1], Lin(-1, ((N, 1),))),
        ([-1, None, -1], Lin(-1, ((N, 1),))),
        ([-5, None, -1], Lin(-1)),
    ],
)
def test_a_backward_clamp_goes_the_way_the_input_went(bounds: list[Expression], start: Lin) -> None:
    made = slices()

    window = made.window(base(), bounds, NONE, settle=True)

    assert window.start == start and window.step == -1
    assert made.regime


def test_a_slice_length_the_input_had_below_zero_is_none() -> None:
    made = slices(i=3)

    # i:1 on the input is 3:1, an empty slice, and the length goes that way
    window = made.window(base(), ["i", 1], NONE, settle=True)

    assert window.length == Lin()
    assert "(assert (not (<= 0 (+ (* (- 1) |arg.i|) 1))))" in made.regime


def test_a_clamp_whose_input_value_is_not_known_is_written_as_a_term() -> None:
    made = slices()
    made.named = lambda part: "e!7"

    window = made.window(base(), [["abs", "i"], None], NONE, settle=True)

    assert window.start == Lin.of("p!0") and not made.regime


@pytest.mark.parametrize(
    ("start", "written"),
    [
        # items[5::-1] on a list the path holds to 6 items or more starts at 5
        (5, Lin(5)),
        # items[-2::-1] on one it holds to 2 or more starts 2 back from the end
        (-2, Lin(-2, ((N, 1),))),
    ],
)
def test_a_backward_bound_the_least_length_settles_is_written_as_it_reads(
    start: int, written: Lin
) -> None:
    made = slices()
    made.least[N] = 6

    window = made.window(base(), [start, None, -1], NONE)

    assert window.start == written and not made.regime and not made.definitions


def test_nested_leaves_out_a_branch_that_fails_and_ends_at_one_that_holds() -> None:
    assert nested([("false", "a"), ("c", "b"), ("true", "d"), ("e", "f")], "g") == "(ite c b d)"
    assert ite("c", "a", "b") == "(ite c a b)"


def test_an_access_through_a_computed_key_names_no_list_of_the_seed() -> None:
    assert access(["[]", "items", ["+", "i", 1]]) is None
    assert access(["[]", "items", 0]) == '["[]", "items", 0]'
