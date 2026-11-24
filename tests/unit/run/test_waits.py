"""Whether a pick's site waits for the last picks, after each answer and its seconds."""

import pytest

from pyct.branches.plan import Plan, plan
from pyct.core.foundation.branch import Branch, Site
from pyct.run.bounds import Bounds
from pyct.run.waits import site_waits, solve_limit
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat


# a-slow-unknown-waits-for-the-last-picks-at-a-quarter-of-the-limit
@pytest.mark.parametrize(
    ("answer", "seconds", "waits"),
    [
        (Unknown(), 2.49, False),
        (Unknown(), 2.5, True),
        (Unknown(), 10.0, True),
        (Unknown(guarded=True), 2.49, False),
        (Unknown(guarded=True), 2.5, True),
        (Timeout(), 0.0, True),
        (Sat({}), 10.0, False),
        (Unsat(), 10.0, False),
    ],
    ids=[
        "unknown-under-a-quarter",
        "unknown-at-a-quarter",
        "unknown-at-the-limit",
        "guarded-unknown-under-a-quarter",
        "guarded-unknown-at-a-quarter",
        "timeout",
        "sat",
        "unsat",
    ],
)
def test_a_site_waits_after_a_timeout_or_an_unknown_that_used_a_quarter_of_its_limit(
    answer: Answer, seconds: float, waits: bool
) -> None:
    assert site_waits(answer, seconds, 10.0) is waits


FORMULA = Site("m.py", 4, 4)


def planned(*, marked: bool) -> Plan:
    forks = (
        Branch(["<", "x", 3], True, Site("m.py", 2, 3)),
        Branch([">", "t", 3], False, Site("m.py", 5, 3), formulas=(FORMULA,) if marked else ()),
    )
    found = plan(forks)
    assert found is not None
    return found


# a-quarter-limit-on-a-formula-s-path
@pytest.mark.parametrize(
    ("left", "marked", "limit"),
    [
        (None, True, 2.5),
        (None, False, 10.0),
        (100.0, True, 2.5),
        (2.0, True, 2.0),
        (2.0, False, 2.0),
        (5.0, True, 2.5),
        (5.0, False, 5.0),
    ],
    ids=[
        "no-budget-marked",
        "no-budget-plain",
        "ample-budget-marked",
        "less-than-the-share-marked",
        "less-than-the-share-plain",
        "between-marked",
        "between-plain",
    ],
)
def test_what_is_left_of_the_budget_still_bounds_a_formula_s_ask(
    left: float | None, marked: bool, limit: float
) -> None:
    assert solve_limit(Bounds(solver_timeout=10.0), left, planned(marked=marked)) == limit


def test_a_fork_before_the_aimed_one_that_reads_a_formula_gives_the_ask_a_quarter() -> None:
    forks = (
        Branch(["<", "t", 3], True, Site("m.py", 5, 3), formulas=(FORMULA,)),
        Branch([">", "x", 3], False, Site("m.py", 7, 3)),
    )
    found = plan(forks)
    assert found is not None

    assert solve_limit(Bounds(solver_timeout=10.0), None, found) == 2.5
