"""Acceptance tests for the guess-inputs-when-stuck story's guess inputs: a guess runs on the real
code as any other input does, labeled ``guess``, its path joining the tree.

Each runs ``run()`` with a fake ``GuessProvider`` that answers fixed guesses.
"""

import json

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.results.coverage import Coverage, Scope
from pyct.results.jsonl import render
from pyct.results.record import Source, StopKind
from pyct.results.trace import render_trace
from tests.acceptance.llm_guesses import (
    FakeGuesses,
    file_of,
    line_of,
    one_thread,  # noqa: F401
    run_guesses,
)


# llm-guess-input-labeled
def test_a_guess_is_labeled_and_counts_in_coverage() -> None:
    provider = FakeGuesses([[{"s": "x"}]])
    handler = file_of("handler")

    ran = run_guesses("targets.guesses.handler::parse", {"s": "a"}, provider)

    [guess] = [record for record in ran.records if record.args == {"s": "x"}]
    coverage = Coverage.of(Scope.of_module(handler), guess.covered_lines)
    assert json.loads(render(guess, coverage))["source"] == "guess"
    assert render_trace(guess, coverage).splitlines()[0] == 'guess {"s": "x"}'
    caught = line_of("handler", "except ValueError:")
    assert {caught, caught + 1} <= ran.result.coverage.covered[handler]


# llm-guess-input-joins-the-tree
def test_a_later_solver_input_starts_from_a_guess_s_path() -> None:
    provider = FakeGuesses([[{"s": "x", "n": 0}]])
    fork = line_of("later", "if n > 5:")

    ran = run_guesses("targets.guesses.later::later", {"s": "a", "n": 0}, provider)

    sources = [record.source for record in ran.records]
    guessed = sources.index(Source.GUESS)
    [solved] = [
        record
        for record in ran.records[guessed + 1 :]
        if record.aim is not None and record.aim.site.line == fork
    ]
    assert solved.source is Source.SOLVER
    assert solved.args == {"s": "x", "n": 6}


# llm-guess-input-stops-on-the-budget
def test_the_budget_ending_during_a_guess_stops_the_rest() -> None:
    # the second spins until the budget ends
    provider = FakeGuesses([[{"s": "x"}, {"s": "fffff"}, {"s": "y"}]])

    ran = run_guesses("targets.guesses.slow::slow", {"s": "a"}, provider, Limits(budget=Budget(3)))

    guessed = [record.args for record in ran.records if record.source is Source.GUESS]
    assert guessed == [{"s": "x"}, {"s": "fffff"}]
    assert ran.result.stopped.kind is StopKind.BUDGET
    assert not [line for line in ran.guess_lines() if line.startswith("llm: dropped guess 3")]
