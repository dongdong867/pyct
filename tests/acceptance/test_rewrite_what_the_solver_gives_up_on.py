"""Acceptance tests for the rewrite-what-the-solver-gives-up-on story: when a run with rewrites is
stuck on a condition whose asks ran out, pyct asks a fake provider for an easier condition,
solves it on the same path, and keeps its input when it takes the wanted side on the real code.

Each runs ``run()`` with a fake ``RewriteProvider`` that answers fixed text; the stderr lines are
the command line's words for the notes the run gave.
"""

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import Source, StopKind
from tests.acceptance.llm_rewrites import (
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)

TEXT = "targets.rewrites.text::exponent"
F = file_of("text")
WANTED = 's == "1e-30"'


# llm-rewrite-when-the-solver-gives-up-keeps-an-input-that-takes-the-side
def test_a_rewrite_s_input_that_takes_the_side_covers_the_line() -> None:
    ran = run_rewrites(TEXT, {"s": "0"}, FakeRewrites([WANTED]))

    assert llm_said(ran.said) == [
        f"llm: rewrite for {F}:2:7: {WANTED}",
        f"llm: rewrite for {F}:2:7: took the wanted side",
    ]
    [found] = [record for record in ran.result.records if record.args == {"s": "1e-30"}]
    assert 3 in found.covered_lines


# llm-rewrite-when-the-solver-gives-up-sends-the-condition-and-its-path
def test_the_request_holds_the_condition_its_path_the_code_the_input_and_the_answer() -> None:
    provider = FakeRewrites(['s == "-1e-30"'])

    run_rewrites("targets.rewrites.path::negative", {"s": "-1"}, provider)

    request = provider.requests[0]
    assert (request.condition.text, request.condition.side) == ("float(s) == -1e-30", True)
    assert [(each.text, each.side) for each in request.earlier] == [('s.startswith("-")', True)]
    assert 'def negative(s):\n    if s.startswith("-"):' in request.code
    assert request.args == (("s", '"-1"'),)
    assert request.answer in ("unknown", "timeout")
    assert request.place == "targets.rewrites.path:3:11"
    assert request.site == f"{file_of('path')}:3:11"


# llm-rewrite-when-the-solver-gives-up-skips-a-condition-that-is-unsat
def test_a_condition_whose_flip_is_unsat_is_not_asked_about() -> None:
    provider = FakeRewrites(["x == 1"])

    ran = run_rewrites("targets.rewrites.never::never", {"x": 1}, provider)

    assert 4 in ran.result.coverage.uncovered[file_of("never")]
    assert provider.requests == []


# llm-rewrite-when-the-solver-gives-up-skips-a-line-with-no-fork
def test_a_line_under_a_condition_with_no_fork_is_not_asked_about() -> None:
    provider = FakeRewrites(["n % 2 == 1"])

    ran = run_rewrites("targets.rewrites.odd::odd", {"n": 0}, provider)

    assert 3 in ran.result.coverage.uncovered[file_of("odd")]
    assert provider.requests == []


# llm-rewrite-when-the-solver-gives-up-waits-until-stuck
def test_a_run_whose_inputs_cover_every_line_never_asks() -> None:
    provider = FakeRewrites(["x > 0"])

    ran = run_rewrites("targets.rewrites.plain::sign", {"x": 0}, provider)

    assert not ran.result.coverage.uncovered[file_of("plain")]
    assert provider.requests == []


# llm-rewrite-when-the-solver-gives-up-asks-once-a-moment
def test_a_condition_missed_at_two_moments_is_asked_about_at_each() -> None:
    provider = FakeRewrites(['s == "1e-29"'])
    # each input adds a pass of the loop and covers no new line, so the run is stuck after 5,
    # and again after 5 more, and stops on the plateau soon after
    limits = Limits(budget=Budget(60), plateau=Plateau(20), solver_timeout=SolverTimeout(1.0))

    ran = run_rewrites("targets.rewrites.loops::loops", {"s": "0", "n": 0}, provider, limits)

    tries = [line for line in llm_said(ran.said) if ", try " in line]
    numbers = [int(line.split(", try ")[1].partition(":")[0]) for line in tries]
    assert numbers[:8] == [1, 2, 3, 4, 5, 6, 7, 8]
    first, second = ran.said.index(tries[3]), ran.said.index(tries[4])
    # the second moment comes after inputs the loop ran between the two
    assert any(line.startswith("input ") for line in ran.said[first:second])


# llm-rewrite-when-the-solver-gives-up-pauses-the-budget-while-waiting
@pytest.mark.serial
def test_the_budget_clock_pauses_while_the_provider_answers() -> None:
    provider = FakeRewrites([WANTED], delay=12.0)
    limits = Limits(budget=Budget(10), solver_timeout=SolverTimeout(1.0))

    ran = run_rewrites(TEXT, {"s": "0"}, provider, limits)

    assert ran.result.stopped.kind is not StopKind.BUDGET
    assert any(3 in record.covered_lines for record in ran.records)


# llm-rewrite-when-the-solver-gives-up-asks-nothing-past-the-budget
def test_a_run_whose_budget_is_spent_when_it_would_be_stuck_asks_nothing() -> None:
    provider = FakeRewrites([WANTED])
    limits = Limits(budget=Budget(1), solver_timeout=SolverTimeout(5.0))

    ran = run_rewrites(TEXT, {"s": "0"}, provider, limits)

    assert ran.result.stopped.kind is StopKind.BUDGET
    assert provider.requests == []


# llm-rewrite-when-the-solver-gives-up-goes-on-after-a-failed-ask
def test_a_failed_ask_is_skipped_and_the_run_goes_on() -> None:
    failed = Unanswered(Why.PROVIDER, "provider error (HTTP 500)", AskCost(1))
    provider = FakeRewrites([failed])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    assert llm_said(ran.said) == ["llm: rewrites ask skipped: provider error (HTTP 500)"]
    assert ran.result.stopped.kind is StopKind.NO_FORK
    assert len(provider.requests) == 1


# llm-rewrite-input-says-rewrite
def test_the_rewrite_s_input_says_rewrite_and_aims_at_the_condition() -> None:
    ran = run_rewrites(TEXT, {"s": "0"}, FakeRewrites([WANTED]))

    [found] = [record for record in ran.records if record.source is Source.REWRITE]
    assert found.args == {"s": "1e-30"}
    assert found.aim is not None
    assert (found.aim.site.file, found.aim.site.line, found.aim.site.col) == (F, 2, 7)
