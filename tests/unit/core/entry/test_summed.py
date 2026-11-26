"""A fork that reads a value a formula gave, or that the formula's own code records, is marked
``summary`` (`pyct.core.entry.in_use.summed`); every other fork is handed back as it is. Here the
forks and the formula's values are made by hand."""

from collections.abc import Iterator

import pytest

from pyct.core.entry import in_use
from pyct.core.foundation.branch import Branch, Expression, SinkItem, Site
from pyct.core.numbers.ints import ConcolicInt

SITE = Site("m.py", 1, 0)


@pytest.fixture(autouse=True)
def live() -> Iterator[None]:
    in_use.start()
    yield
    in_use.forget()
    KEPT.clear()


def given(expression: Expression) -> ConcolicInt:
    """A tracked int a formula gave, with the term ``expression``."""
    sink: list[SinkItem] = []
    return ConcolicInt.made(2, expression=expression, sink=sink)


# each fork marked, kept as the input's tally keeps its forks, so that no id a walk found clean
# is taken by a new term
KEPT: list[Branch] = []


def fork(expression: Expression) -> Branch:
    return Branch(expression, True, SITE)


def marked(expression: Expression) -> bool:
    kept = in_use.summed(fork(expression))
    KEPT.append(kept)
    return kept.summary


def test_a_fork_after_the_loop_that_reads_the_formula_s_value_is_marked() -> None:
    term: Expression = ["+", "t", ["count", "s", "'z'"]]
    before = marked(["==", "s", "'q'"])
    in_use.gave((given(term),))

    assert (before, marked([">", term, 3]), marked(["==", "s", "'r'"])) == (False, True, False)


def test_a_fork_the_formula_s_own_code_records_is_marked() -> None:
    in_use.USING.forming = True
    try:
        own = marked([">", ["count", "s", "'z'"], 5])
    finally:
        in_use.USING.forming = False

    assert (own, marked(["==", "s", "'r'"])) == (True, False)


def test_a_fork_with_no_formula_value_in_the_input_is_handed_back_as_it_is() -> None:
    held = fork([">", "x", 3])

    assert in_use.summed(held) is held


def test_a_fork_after_a_dropped_formula_is_not_marked() -> None:
    # the formula ran on the term and recorded a fork, then was dropped, so it gave no value
    term: Expression = ["count", "s", "'z'"]
    in_use.USING.forming = True
    try:
        own = marked([">", term, 5])
    finally:
        in_use.USING.forming = False

    assert (own, marked([">", term, 3])) == (True, False)


def test_a_part_found_clean_is_not_walked_again_after_a_later_match_in_the_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    walked = in_use._reads_a_formula
    known: list[bool] = []

    def watched(
        expression: Expression, reads: dict[int, list[Expression]], clean: set[int]
    ) -> bool:
        # each `u == "zzx"` is a new list; the term of `u` inside it is the same one
        assert isinstance(expression, list)
        known.append(id(expression[1]) in clean)
        return walked(expression, reads, clean)

    monkeypatch.setattr(in_use, "_reads_a_formula", watched)
    u: Expression = ["+", "s", "'x'"]
    first = given(["count", "s", "'z'"])
    in_use.gave((first,))
    before = marked(["==", u, "'zzx'"])
    second = given(["count", "s", "'z'"])
    in_use.gave((second,))

    assert (before, marked(["==", u, "'zzx'"])) == (False, False)
    # the second `u == "zzx"` comes after the second match, and `u` is known clean
    assert known == [False, True]


def test_a_part_found_clean_that_holds_a_term_handed_back_is_walked_again() -> None:
    t: Expression = ["count", "s", "'z'"]
    u: Expression = ["+", t, 1]
    in_use.gave((given(["+", "n", ["count", "s", "'a'"]]),))
    before = marked(["==", u, 9])
    # a formula hands back `t`'s term as it was given it, which `u`'s holds
    in_use.gave((given(t),))

    # after the first match, `u == 9` finds `u`'s term clean; the second formula then hands back
    # `t`'s term, which `u`'s holds, so `u > 3` holds a formula's term
    assert (before, marked([">", u, 3])) == (False, True)
