"""Acceptance tests for the guess-inputs-when-stuck story: when a run with guesses is stuck on
lines no other tool takes, pyct asks a fake provider once for inputs that reach them, and runs
each guess on the real code.

Each runs ``run()`` with a fake ``GuessProvider`` that answers fixed guesses, and the fakes of
summaries or rewrites where a criterion names those tools; the stderr lines are the command
line's words for the notes the run gave.
"""

import time

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.config.solver_timeout import SolverTimeout
from pyct.results.causes import Reason
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import Source, StopKind
from pyct.rewrite.provider import Side
from tests.acceptance.llm_guesses import (
    FakeGuesses,
    Others,
    file_of,
    line_of,
    one_thread,  # noqa: F401
    run_guesses,
)
from tests.acceptance.llm_rewrites import FakeRewrites
from tests.acceptance.llm_summaries import COUNT, FakeSummaries

HANDLER = "targets.guesses.handler::parse"
H = file_of("handler")
# the `except ValueError:` line of handler.py, and the line it holds
CAUGHT = line_of("handler", "except ValueError:")
# a plateau that ends a run soon after its first moment
SHORT = Limits(plateau=Plateau(8))


# llm-guess-for-a-stuck-line-handler
def test_a_handler_line_gets_a_guess_that_reaches_it() -> None:
    provider = FakeGuesses([[{"s": "x", "n": 0}]])
    counted = file_of("counted")
    caught = line_of("counted", "except ValueError:")

    ran = run_guesses("targets.guesses.counted::counted", {"s": "a", "n": 1}, provider, SHORT)

    asked = f"llm: guesses for {counted}:{caught}, {counted}:{caught + 1} (handler)"
    reached = f"llm: guess 1 reached {counted}:{caught}, {counted}:{caught + 1}"
    assert ran.guess_lines()[:2] == [asked, reached]
    # 5 inputs in a row covered no new line before the ask
    assert ran.said.index(asked) == ran.said.index("input 6") + 1
    assert ran.said.index(asked) < ran.said.index("input 7") < ran.said.index(reached)


# llm-guess-for-a-stuck-line-no-source-on-an-empty-tree
def test_a_no_fork_line_with_no_source_gets_guesses_on_an_empty_tree() -> None:
    provider = FakeGuesses([[]])
    seven = line_of("boxed", 'return "seven"')

    ran = run_guesses("targets.guesses.boxed::boxed", {"x": 3}, provider)

    assert (
        ran.guess_lines()[0]
        == f"llm: guesses for {file_of('boxed')}:{seven} (no fork, no source found)"
    )
    assert ran.said.index(ran.guess_lines()[0]) == ran.said.index("input 1") + 1
    assert ran.result.stopped.kind is StopKind.NO_FORK


# llm-guess-for-a-stuck-line-one-ask-for-every-line
def test_one_ask_covers_every_line_guesses_take() -> None:
    # the first four end before line 11, the fifth raises into the handler
    first = [{"s": s, "t": "y"} for s in "bcdex"]
    provider = FakeGuesses([[*first, {"s": "f", "t": "1"}, {"s": "g", "t": "2"}]])
    both = file_of("both")
    caught, total = line_of("both", "except ValueError:"), line_of("both", "return total")

    ran = run_guesses("targets.guesses.both::both", {"s": "a", "t": "x"}, provider)

    assert len(provider.requests) == 1
    assert ran.guess_lines()[0] == (
        f"llm: guesses for {both}:{caught}, {both}:{caught + 1} (handler),"
        f" {both}:{total} (ended before)"
    )
    assert [record.args for record in ran.records if record.source is Source.GUESS] == first
    assert ran.guess_lines()[-2:] == [
        "llm: dropped guess 6: more than 5 guesses",
        "llm: dropped guess 7: more than 5 guesses",
    ]


# llm-guess-for-a-stuck-line-ended-before
def test_an_ended_before_line_gets_guesses() -> None:
    provider = FakeGuesses([[{"s": "a"}]])
    ended = file_of("ended")
    line = line_of("ended", "return value")

    ran = run_guesses("targets.guesses.ended::ended", {"s": "x"}, provider)

    assert ran.guess_lines() == [
        f"llm: guesses for {ended}:{line} (ended before)",
        f"llm: guess 1 reached {ended}:{line}",
    ]
    [asked] = provider.requests[0].lines
    assert asked.cause == "ended before"


# llm-guess-for-a-stuck-line-after-a-tool-gave-up
def test_a_line_whose_summary_gave_up_gets_guesses() -> None:
    summaries = FakeSummaries([COUNT, "I cannot summarize this loop."])
    provider = FakeGuesses([[]])
    loops = file_of("loops")
    lots = line_of("loops", 'return "lots"')

    ran = run_guesses(
        "targets.guesses.loops::two", {"s": "ab"}, provider, SHORT, Others(summaries=summaries)
    )

    asked = f"llm: guesses for {loops}:{lots} (summary gave up)"
    assert ran.guess_lines()[0] == asked
    summary_lines = [line for line in ran.llm_said() if line.startswith("llm: summar")]
    assert ran.said.index(summary_lines[-1]) < ran.said.index(asked)
    # the loop whose summary held is not asked about
    assert [each.lines for each in provider.requests[0].lines] == [(lots,)]


# llm-guess-for-a-stuck-line-after-a-rewrite-gave-up
def test_a_line_whose_rewrite_gave_up_gets_guesses() -> None:
    rewrites = FakeRewrites(['s == "1e-30"', "I cannot rewrite it."])
    provider = FakeGuesses([[]])
    text = file_of("text")
    second = line_of("text", "return 2")
    limits = Limits(solver_timeout=SolverTimeout(1.0))

    ran = run_guesses(
        "targets.guesses.text::exponents",
        {"s": "0", "t": "0"},
        provider,
        limits,
        Others(rewrites=rewrites),
    )

    asked = f"llm: guesses for {text}:{second} (rewrite gave up)"
    assert ran.guess_lines()[0] == asked
    rewrite_lines = [line for line in ran.llm_said() if line.startswith("llm: rewrite ")]
    assert f"llm: rewrite for {text}:{second - 1}:7, try 4: " in "\n".join(rewrite_lines)
    assert ran.said.index(rewrite_lines[-1]) < ran.said.index(asked)
    # the condition whose rewrite took the wanted side is not asked about
    assert [each.lines for each in provider.requests[0].lines] == [(second,)]


# llm-guess-for-a-stuck-line-takes-a-switched-off-tool-s-line
def test_guesses_take_a_switched_off_tool_s_line() -> None:
    provider = FakeGuesses([[]])
    many = line_of("loops", 'return "many"')

    ran = run_guesses("targets.guesses.loops::counts", {"s": "ab"}, provider, SHORT)

    assert ran.guess_lines()[0] == f"llm: guesses for {file_of('loops')}:{many} (no fork)"


# llm-guess-for-a-stuck-line-skips-what-no-guess-helps
def test_no_guess_ask_for_a_line_no_guess_helps() -> None:
    provider = FakeGuesses([[{"x": 4}]])

    ran = run_guesses("targets.guesses.skipped::skipped", {"x": 3}, provider)

    entries = ran.result.why_uncovered
    assert {entry.reason for entry in entries} == {Reason.NOT_CALLED, Reason.NOT_TAKEN}
    tries = sorted(
        (entry.tries.unsat, entry.tries.left_the_plan) for entry in entries if entry.tries
    )
    assert tries == [(0, 1), (1, 0)]
    assert provider.requests == []
    assert ran.guess_lines() == []


# llm-guess-for-a-stuck-line-at-most-three-moments
def test_guesses_ask_in_three_moments_at_most() -> None:
    provider = FakeGuesses([[]])
    limits = Limits(budget=Budget(60), plateau=Plateau(30))

    ran = run_guesses("targets.guesses.counted::counted", {"s": "a", "n": 1}, provider, limits)

    asks = [line for line in ran.guess_lines() if line.startswith("llm: guesses for ")]
    assert len(asks) == len(provider.requests) == 3
    after = ran.said[ran.said.index(asks[-1]) :]
    # the run went on past the inputs in a row that would have brought a fourth moment
    assert sum(line.startswith("input ") for line in after) > 10


# llm-guess-for-a-stuck-line-sends-what-pyct-saw
def test_the_request_holds_each_line_its_way_and_the_furthest_input() -> None:
    provider = FakeGuesses([[]])
    caught = line_of("way", "except ValueError:")

    run_guesses("targets.guesses.way::deep", {"s": "a", "n": 0}, provider)

    request = provider.requests[0]
    assert request.place == "targets.guesses.way::deep#1"
    assert request.signature == "(s: str, n: int) -> int"
    assert "def deep(s: str, n: int) -> int:\n    if n > 10:" in request.code
    [asked] = request.lines
    assert (asked.module, asked.lines, asked.cause) == (
        "targets.guesses.way",
        (caught, caught + 1),
        "handler",
    )
    assert asked.conditions == (Side("n > 10", True),)
    assert (asked.furthest, asked.ended) == ('{"s": "a", "n": 11}', "returned")


# llm-guess-for-a-stuck-line-ask-failed
def test_an_unanswered_guess_ask_is_said_and_the_run_goes_on() -> None:
    failed = Unanswered(Why.TIMED_OUT, "no reply in 30 s", AskCost(1))
    provider = FakeGuesses([failed])

    ran = run_guesses(HANDLER, {"s": "a"}, provider)

    assert ran.guess_lines() == [
        f"llm: guesses for {H}:{CAUGHT}, {H}:{CAUGHT + 1} (handler)",
        "llm: guesses ask skipped: no reply in 30 s",
    ]
    assert ran.result.stopped.kind is StopKind.NO_FORK


# llm-guess-for-a-stuck-line-wait-not-counted
@pytest.mark.serial
def test_the_wait_for_guesses_is_not_counted() -> None:
    provider = FakeGuesses([[{"s": "x"}]], delay=8.0)
    started = time.monotonic()

    ran = run_guesses(HANDLER, {"s": "a"}, provider, Limits(budget=Budget(10)))

    used = provider.asked_at[0] - started
    left = ran.result.deadline - provider.answered_at[0]
    # the budget left after the reply is what was left as the ask went out
    assert 10 - used - 1.0 < left <= 10
    assert ran.result.stopped.kind is not StopKind.BUDGET
