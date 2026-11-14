"""Acceptance tests for the ask-for-a-stuck-loop-s-summary story through ``run()``: pyct reads the
reply's formula, checks its form, checks it on the loop's past runs in a forked child, and checks
that pyct follows the values it gives, saying each step on stderr.

Each run has summaries on with a fake provider; no test calls a model.
"""

import pytest

from pyct.results.record import StopKind
from pyct.run import summary_checks
from tests.acceptance.llm_summaries import (
    COUNT,
    COUNTED,
    COUNTS,
    SEED,
    F,
    FakeSummaries,
    G,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)

TALLIES = "targets.summaries.loops::tallies"
AT = f"llm: summary for the loop at {F}:10"


def summary_lines(done: Summarized) -> list[str]:
    return [line for line in done.llm_said() if line.startswith("llm: summary for")]


# llm-summary-for-a-stuck-loop-asked-and-checked
def test_a_formula_that_gives_every_past_run_s_value_and_one_pyct_follows_is_checked() -> None:
    provider = FakeSummaries([COUNT])

    done = run_summaries(COUNTS, SEED, provider)

    [request] = provider.requests
    assert request.place == "targets.why.stuck:10:4"
    assert summary_lines(done) == [
        f'{AT}: t = t + s.count("z")',
        f"{AT}: checked on {provider.inputs_then[0]} past runs",
    ]


# llm-summary-for-a-stuck-loop-comprehension
def test_a_comprehension_s_value_is_asked_about_and_checked() -> None:
    provider = FakeSummaries([code_reply('def summary(s):\n    return {"t": s.count("z")}')])

    done = run_summaries(COUNTED, SEED, provider)

    [request] = provider.requests
    assert (request.place, request.changed) == ("targets.why.stuck:19:11", ("t",))
    at = f"llm: summary for the loop at {F}:19"
    assert summary_lines(done) == [
        f'{at}: t = s.count("z")',
        f"{at}: checked on {provider.inputs_then[0]} past runs",
    ]


# llm-summary-for-a-stuck-loop-each-changed-value
def test_one_ask_names_each_changed_value_and_the_line_writes_a_formula_for_each() -> None:
    formula = (
        "def summary(s, ups, downs):\n"
        '    return {"ups": ups + s.count("u"), "downs": downs + s.count("d")}'
    )
    provider = FakeSummaries([code_reply(formula)])

    done = run_summaries(TALLIES, SEED, provider)

    [request] = provider.requests
    assert request.changed == ("downs", "ups")
    at = f"llm: summary for the loop at {G}:8"
    assert summary_lines(done) == [
        f'{at}: ups = ups + s.count("u"); downs = downs + s.count("d")',
        f"{at}: checked on {provider.inputs_then[0]} past runs",
    ]


# llm-summary-for-a-stuck-loop-fails-a-past-run
def test_a_formula_that_misses_a_past_run_s_value_fails_its_try() -> None:
    provider = FakeSummaries([code_reply('def summary(s, t):\n    return {"t": len(s)}')])

    done = run_summaries(COUNTS, SEED, provider)

    assert summary_lines(done) == [
        f"{AT}: t = len(s)",
        f"{AT}, try 1: at input 1, t was 0, the formula gave 2",
    ]
    assert len(provider.requests) == 1
    assert done.result.stopped.kind is StopKind.NO_GAIN
    assert len(done.records) > provider.inputs_then[0]


# llm-summary-for-a-stuck-loop-value-not-tracked
def test_a_formula_whose_value_pyct_does_not_follow_fails_its_try() -> None:
    formula = 'def summary(s, t):\n    return {"t": t + s.encode().count(b"z")}'
    provider = FakeSummaries([code_reply(formula)])

    done = run_summaries(COUNTS, SEED, provider)

    assert summary_lines(done) == [
        f'{AT}: t = t + s.encode().count(b"z")',
        f"{AT}, try 1: pyct does not follow encode",
    ]


# llm-summary-for-a-stuck-loop-form-refused
def test_a_formula_outside_the_form_fails_its_try_and_nothing_of_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refused(*_: object) -> object:
        raise AssertionError("a refused formula ran")

    monkeypatch.setattr(summary_checks, "run_model", refused)
    formula = 'def summary(s, t):\n    return {"t": t + sum(1 for c in s if c == "z")}'
    provider = FakeSummaries([code_reply(formula)])

    done = run_summaries(COUNTS, SEED, provider)

    assert summary_lines(done) == [f"{AT}, try 1: a formula may not use a comprehension"]
