"""Why a line was missed where paths join, raises are caught, and nothing shows a side."""

import logging
import time
from pathlib import Path

import pytest

from pyct.core.branch import ForkSite, Site
from pyct.results.why import Condition, Reason, Tries, Walked, WhyEntry
from tests.unit.results.test_why import fork, module, why

OR_JOIN = """\
def f(x):
    if x != x or x + 1 == x:
        return "never"
    return "always"
"""


def test_a_line_two_sides_reach_names_the_first_side_no_input_took(tmp_path: Path) -> None:
    file = module(tmp_path, OR_JOIN)
    forks = (fork(file, 2, 7, taken=False), fork(file, 2, 17, taken=False))
    site = Site(file=file, line=2, col=7)

    (entry,) = why(file, ({3}, {2, 4}), [Walked(forks, failed=False, lines=frozenset({2, 4}))])

    assert entry.reason is Reason.NOT_TAKEN
    assert entry.condition == Condition(site=site, side=True)


def test_ended_before_needs_an_input_that_ended(tmp_path: Path) -> None:
    source = """\
    def f(x):
        if x > 0:
            y = 1
        else:
            y = 2
        return y
    """
    file = module(tmp_path, source)
    walked = [Walked(forks=(), failed=False, lines=frozenset({2, 3, 6}))]

    (entry,) = why(file, ({5}, {2, 3, 6}), walked)

    # the input took the true side and returned; the false side, plain, is why
    assert entry.reason is Reason.NO_FORK
    assert entry.condition == Condition(site=Site(file=file, line=2, col=7), side=False)


def test_a_raise_a_handler_caught_on_the_way_ended_the_input(tmp_path: Path) -> None:
    source = """\
    def f(x):
        try:
            y = int("q")
            return y
        except ValueError:
            return 0
    """
    file = module(tmp_path, source)
    walked = [Walked(forks=(), failed=False, lines=frozenset({2, 3, 5, 6}))]

    (entry,) = why(file, ({4}, {2, 3, 5, 6}), walked)

    assert entry == WhyEntry(file=file, lines=(4,), reason=Reason.ENDED_BEFORE)


def test_an_operation_s_fork_does_not_answer_for_the_test_at_its_column(tmp_path: Path) -> None:
    source = """\
    def f(s):
        if s[0] != s[0]:
            return 1
        return 2
    """
    file = module(tmp_path, source)
    forks = (fork(file, 2, 7, taken=True, raising=True), fork(file, 2, 7, taken=False))
    site = Site(file=file, line=2, col=7)
    tries = {ForkSite(site): Tries(unsat=1), ForkSite(site, raising=True): Tries(not_tried=1)}

    (entry,) = why(
        file, ({3}, {2, 4}), [Walked(forks, failed=False, lines=frozenset({2, 4}))], tries
    )

    assert entry.reason is Reason.NOT_TAKEN
    assert entry.condition == Condition(site=site, side=True)
    assert entry.tries == Tries(unsat=1)


def test_a_ternary_s_side_is_not_blamed_before_a_condition_that_shows_it(tmp_path: Path) -> None:
    source = """\
    def f(x):
        y = 1 if x > 0 else 2
        if y > 5:
            return 1
        return 0
    """
    file = module(tmp_path, source)
    walked = [Walked(forks=(), failed=False, lines=frozenset({2, 3, 5}))]

    (entry,) = why(file, ({4}, {2, 3, 5}), walked)

    # no line tells the ternary's sides apart, so the plain test the line needs is named
    assert entry.reason is Reason.NO_FORK
    assert entry.condition == Condition(site=Site(file=file, line=3, col=7), side=True)


def test_an_except_block_no_raise_reached_is_the_handler_s_though_inputs_ended_first(
    tmp_path: Path,
) -> None:
    source = """\
    def f(x):
        y = int("x")
        try:
            z = y
        except ValueError:
            return 0
        return z
    """
    file = module(tmp_path, source)
    walked = [Walked(forks=(), failed=True, lines=frozenset({2}))]

    entries = why(file, ({3, 4, 5, 6, 7}, {2}), walked)

    # one cause, one entry: the lines around the try share the ending
    assert [(entry.lines, entry.reason) for entry in entries] == [
        ((3, 4, 7), Reason.ENDED_BEFORE),
        ((5, 6), Reason.HANDLER),
    ]


def test_ended_before_looks_past_an_input_that_returned_to_one_that_ended(
    tmp_path: Path,
) -> None:
    source = """\
    def ends(x):
        y = int(x)
        return y + 1
    """
    file = module(tmp_path, source)
    # the first input reached line 2 and returned: nothing in this code shows how
    walked = [
        Walked(forks=(), failed=False, lines=frozenset({2})),
        Walked(forks=(), failed=True, lines=frozenset({2})),
    ]

    assert why(file, ({3}, {2}), walked) == (
        WhyEntry(file=file, lines=(3,), reason=Reason.ENDED_BEFORE),
    )


def test_a_side_only_a_ternary_leads_to_is_named_when_nothing_else_explains_the_line(
    tmp_path: Path,
) -> None:
    source = """\
    def f(x):
        y = 1 if x > 0 else 2
        return y
    """
    file = module(tmp_path, source)
    # a run that covered line 2 and not line 3, and did not end: nothing but the ternary is left
    walked = [Walked(forks=(), failed=False, lines=frozenset({2}))]

    (entry,) = why(file, ({3}, {2}), walked)

    assert entry.reason is Reason.NO_FORK
    assert entry.condition is not None
    assert entry.condition.site.line == 2


def test_a_reaching_side_its_fork_shows_is_named_before_a_ternary_s(tmp_path: Path) -> None:
    source = """\
    def f(x, z):
        y = 1 if x > 0 else 2
        if z > 0 or y > 5:
            return 1
        return 0
    """
    file = module(tmp_path, source)
    walked = [
        Walked(forks=(fork(file, 3, 7, taken=False),), failed=False, lines=frozenset({2, 3, 5}))
    ]

    (entry,) = why(file, ({4}, {2, 3, 5}), walked)

    assert entry.reason is Reason.NOT_TAKEN
    assert entry.condition == Condition(site=Site(file=file, line=3, col=7), side=True)


def test_two_tests_at_one_site_take_their_own_sides(tmp_path: Path) -> None:
    source = """\
    def f(x):
        if x < 5 < x:
            return 1
        return 2
    """
    file = module(tmp_path, source)
    site = Site(file=file, line=2, col=7)
    # `x < 5` taken, then `5 < x` not taken, both at 2:7
    forks = (fork(file, 2, 7, taken=True), fork(file, 2, 7, taken=False))
    walked = [Walked(forks, failed=False, lines=frozenset({2, 4}))]

    (entry,) = why(file, ({3}, {2, 4}), walked, {ForkSite(site): Tries(unsat=1)})

    assert entry.reason is Reason.NOT_TAKEN
    assert entry.condition == Condition(site=site, side=True)
    assert entry.tries == Tries(unsat=1)


CAUGHT_IN_A_LOOP = """\
TABLE = {"k": 1}


def f(x):
    total = 0
    for i in range(2):
        try:
            v = TABLE["z"]
            total += v
        except KeyError:
            continue
    return total + x
"""


def test_a_raise_the_function_caught_before_the_line_ended_the_input(tmp_path: Path) -> None:
    file = module(tmp_path, CAUGHT_IN_A_LOOP)
    lines = frozenset({5, 6, 7, 8, 10, 11, 12})

    entries = why(file, ({1, 4, 9}, set(lines)), [Walked(forks=(), failed=False, lines=lines)])

    assert entries[-1] == WhyEntry(file=file, lines=(9,), reason=Reason.ENDED_BEFORE)


def test_an_input_that_neither_ended_nor_raised_is_never_said_to_have_ended(
    tmp_path: Path,
) -> None:
    source = """\
    def f(x):
        y = 1 if x > 0 else 2
        return y
    """
    file = module(tmp_path, source)

    (entry,) = why(file, ({3}, {2}), [Walked(forks=(), failed=False, lines=frozenset({2}))])

    # nothing shows which side the ternary took, and nothing ended: the ternary is named
    assert entry.reason is Reason.NO_FORK


GENERATOR = """\
def numbers(x):
    yield x
    y = x + 1
    yield y


def first(x):
    return next(numbers(x))
"""


def test_a_generator_left_at_a_yield_is_suspended_there(tmp_path: Path) -> None:
    file = module(tmp_path, GENERATOR)
    lines = frozenset({2, 8})

    entries = why(file, ({1, 3, 4, 7}, set(lines)), [Walked(forks=(), failed=False, lines=lines)])

    assert entries[-1] == WhyEntry(file=file, lines=(3, 4), reason=Reason.SUSPENDED, at_yield=2)


def test_a_generator_that_failed_past_its_yield_ended_before_the_line(tmp_path: Path) -> None:
    file = module(tmp_path, GENERATOR)
    lines = frozenset({2, 8})

    entries = why(file, ({1, 3, 4, 7}, set(lines)), [Walked(forks=(), failed=True, lines=lines)])

    assert entries[-1] == WhyEntry(file=file, lines=(3, 4), reason=Reason.ENDED_BEFORE)


def test_a_raise_out_of_a_frame_its_caller_caught_ended_the_input(tmp_path: Path) -> None:
    source = """\
    def f(x):
        y = int(x)
        return y
    """
    file = module(tmp_path, source)
    # line 2 ran and line 3 did not, yet the input did not fail: line 2 raised out of the frame,
    # and the frame's caller caught it
    walked = [Walked(forks=(), failed=False, lines=frozenset({2}))]

    assert why(file, ({3}, {2}), walked) == (
        WhyEntry(file=file, lines=(3,), reason=Reason.ENDED_BEFORE),
    )


def test_facts_no_cause_explains_are_logged_as_such(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = """\
    def f(x):
        try:
            y = 1
        finally:
            z = 2
        return z
    """
    file = module(tmp_path, source)
    # the finally body ran with the try body before it never run: facts no run of this code
    # gives, so no cause explains them and the log says so
    walked = [Walked(forks=(), failed=False, lines=frozenset({5, 6}))]

    with caplog.at_level(logging.WARNING, logger="pyct.results.why"):
        (entry,) = why(file, ({3}, {5, 6}), walked)

    assert entry.reason is Reason.ENDED_BEFORE
    said = f"no cause explains line 3 of {file}; it is put down as ended before"
    assert caplog.messages == [said]


def test_a_long_generator_s_causes_take_near_linear_time(tmp_path: Path) -> None:
    ifs = "".join(f"    if x == {k}:\n        y += {k}\n" for k in range(200))
    after = "".join(f"    y += {k}\n" for k in range(20))
    source = f"def gen(x):\n    y = 0\n{ifs}    yield y\n{after}    yield y\n"
    file = module(tmp_path, source)
    yield_line = 3 + 2 * 200
    tests = frozenset(range(3, yield_line, 2))
    # 201 inputs, each through every test and one of the if bodies, then left at the yield
    walked = [
        Walked(forks=(), failed=False, lines=frozenset({2, yield_line, 4 + 2 * k}) | tests)
        for k in range(200)
    ]
    walked.append(Walked(forks=(), failed=False, lines=frozenset({2, yield_line}) | tests))
    covered = frozenset().union(*(each.lines for each in walked))
    uncovered = frozenset(range(yield_line + 1, yield_line + 22))

    started = time.perf_counter()
    entries = why(file, (set(uncovered), set(covered)), walked)
    spent = time.perf_counter() - started

    assert [entry.reason for entry in entries] == [Reason.SUSPENDED]
    assert entries[0].lines == tuple(sorted(uncovered))
    # the per-line, per-input walk this replaced took 15 s here without coverage's tracing,
    # and 0.6 s now; the bound leaves room for tracing and a busy machine
    assert spent < 5.0, spent
