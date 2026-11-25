"""Acceptance tests for the guess-inputs-when-stuck story's dropped guesses: a guess that fails a
seed check, repeats an input, or comes past the fifth does not run.

Each runs ``run()`` with a fake ``GuessProvider`` that answers fixed guesses.
"""

from pyct.results.record import Source
from tests.acceptance.harness import run_pyct
from tests.acceptance.llm_guesses import (
    FakeGuesses,
    one_thread,  # noqa: F401
    run_guesses,
)

TYPED = "targets.guesses.typed::typed"


# llm-guess-dropped-fails-a-seed-check
def test_a_guess_that_fails_a_seed_check_is_dropped() -> None:
    provider = FakeGuesses([[{"y": 1}, {"x": "a"}]])

    ran = run_guesses(TYPED, {"x": 1}, provider)

    plain_names = run_pyct(TYPED, '{"y": 1}').stderr.strip()
    plain_types = run_pyct(TYPED, '{"x": "a"}').stderr.strip()
    assert ran.guess_lines()[1:] == [
        f"llm: dropped guess 1: {plain_names}",
        f"llm: dropped guess 2: {plain_types}",
    ]
    assert [record.source for record in ran.records] == [Source.SEED]


# llm-guess-dropped-repeats-an-input
def test_a_guess_that_repeats_an_input_is_dropped() -> None:
    provider = FakeGuesses([[{"x": 1}, {"x": 2}, {"x": 2}]])

    ran = run_guesses(TYPED, {"x": 1}, provider)

    [number] = [n for n, record in enumerate(ran.records, 1) if record.args == {"x": 2}]
    assert ran.records[number - 1].source is Source.GUESS
    assert ran.guess_lines()[1:] == [
        "llm: dropped guess 1: same input as input 1",
        f"llm: dropped guess 3: same input as input {number}",
    ]
    assert ran.said.index(f"input {number}") < ran.said.index(ran.guess_lines()[2])


# llm-guess-dropped-repeats-an-input, its parameters written in another order
def test_a_guess_that_repeats_an_input_in_another_key_order_is_dropped() -> None:
    provider = FakeGuesses([[{"s": "a", "n": 0}]])

    ran = run_guesses("targets.guesses.way::deep", {"n": 0, "s": "a"}, provider)

    assert ran.guess_lines()[1:] == ["llm: dropped guess 1: same input as input 1"]
    assert Source.GUESS not in [record.source for record in ran.records]


# llm-guess-dropped-past-the-fifth
def test_guesses_past_the_fifth_are_dropped() -> None:
    # the first five are hex digits, which return; the last two would raise into the handler
    guesses = [{"s": s} for s in "bcdefgh"]
    provider = FakeGuesses([guesses])

    ran = run_guesses("targets.guesses.handler::parse", {"s": "a"}, provider)

    run = [record.args for record in ran.records if record.source is Source.GUESS]
    assert run == guesses[:5]
    assert ran.guess_lines()[1:] == [
        "llm: dropped guess 6: more than 5 guesses",
        "llm: dropped guess 7: more than 5 guesses",
    ]
