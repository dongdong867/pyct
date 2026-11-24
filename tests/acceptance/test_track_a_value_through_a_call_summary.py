"""Acceptance tests for the track-a-value-through-a-call-summary story: once a loss site's formula
passes its checks it comes into use, the input its check used runs again, and in each later input
the site's answer comes out tracked with the formula's term, so each condition after it forks.

Each run through ``run()`` has summaries on with a fake provider, its package intercepted with the
recording of each loop's runs, and each input in a forked child; each run through ``pyct run``
has its base URLs pointed at a stub on localhost. No test calls a model.
"""

import json
import textwrap
from pathlib import Path

from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.core.foundation.branch import Branch
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.results.record import InputRecord, Source, StopKind
from pyct.run.isolation import Isolation
from tests.acceptance.harness import input_lines, summary_line
from tests.acceptance.llm_stub import Stub, llm_lines, llm_run
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import (
    CAP,
    DEDENTED,
    DIVIDED,
    FORKED,
    MOD,
    QUARTER,
    SHIFTED,
    SQUARED,
    WRAPPED,
    at,
    place,
    places,
)

# the term of `QUARTER`'s answer, as a fork's expression writes it
QUARTER_TERM = ["%", "n", 4]
# a run that goes on well past its first turn
LONGER = Limits(plateau=Plateau(20))


def summarized(
    spec: str,
    seed: dict[str, object],
    reply: str,
    isolation: Isolation = Isolation.AUTO,
) -> Summarized:
    """``spec`` run from ``seed``, the provider answering ``reply``, past the formula's ``checked
    on`` line, each input where ``isolation`` says."""
    provider = FakeSummaries([reply])
    done = run_summaries(spec, seed, provider, LONGER, isolation)
    assert after_checked(done), done.said
    return done


def after_checked(done: Summarized) -> list[InputRecord]:
    """The inputs that ran after the first formula's ``checked on`` line."""
    checked = next(at for at, line in enumerate(done.said) if ": checked on " in line)
    before = sum(1 for line in done.said[:checked] if line.startswith("input "))
    return done.records[before:]


def before_checked(done: Summarized) -> list[InputRecord]:
    after = after_checked(done)
    return done.records[: len(done.records) - len(after)]


def forks_at(record: InputRecord, line: int) -> list[Branch]:
    return [each for each in record.forks if each.site.line == line]


def holds(expression: object, name: str) -> bool:
    """Whether the expression reads ``name`` at any depth."""
    if expression == name:
        return True
    return isinstance(expression, list) and any(holds(each, name) for each in expression)


def n_of(record: InputRecord) -> int:
    n = record.args["n"]
    assert isinstance(n, int)
    return n


def downgraded(record: InputRecord, name: str) -> list[str]:
    """The sites, written ``file:line:col``, at which the input names a downgrade of ``name``."""
    return [
        f"{each.site.file}:{each.site.line}:{each.site.col}"
        for each in record.downgrades
        if each.name == name and each.site is not None
    ]


# llm-summary-for-a-call-pyct-cannot-follow-in-use-tracks-the-answer
def test_an_input_after_the_check_forks_on_the_formula_s_term() -> None:
    done = summarized(SHIFTED, {"n": 3}, QUARTER)

    for record in after_checked(done):
        expressions = [each.expression for each in forks_at(record, 16)]
        assert expressions == [["==", QUARTER_TERM, 2]], record


# llm-summary-for-a-call-pyct-cannot-follow-in-use-in-a-fresh-interpreter
def test_an_input_in_a_fresh_interpreter_forks_on_the_formula_s_term() -> None:
    done = summarized(SHIFTED, {"n": 3}, QUARTER, Isolation.FRESH)

    for record in after_checked(done):
        expressions = [each.expression for each in forks_at(record, 16)]
        assert expressions == [["==", QUARTER_TERM, 2]], record


# llm-summary-for-a-call-pyct-cannot-follow-in-use-records-no-downgrade
def test_an_input_after_the_check_names_no_downgrade_at_the_site() -> None:
    done = summarized(SHIFTED, {"n": 3}, QUARTER)

    for record in before_checked(done):
        assert downgraded(record, "__pow__") == [at(11, 11)], record
    for record in after_checked(done):
        assert downgraded(record, "__pow__") == [], record


# llm-summary-for-a-call-pyct-cannot-follow-in-use-reaches-the-missed-line
def test_an_input_the_formula_s_fork_gave_covers_the_missed_line() -> None:
    done = summarized(SHIFTED, {"n": 3}, QUARTER)

    [two] = [record for record in after_checked(done) if 17 in record.covered_lines]
    assert n_of(two) % 4 == 2
    assert two.source is Source.SUMMARY


# llm-summary-for-a-call-pyct-cannot-follow-in-use-formula-if-forks-at-the-site
def test_a_formula_s_own_if_forks_at_the_site_before_the_later_condition() -> None:
    # from n = 1, the cap holds while n % 4 is below 3, and is wrong at 3
    done = summarized(SHIFTED, {"n": 1}, CAP)

    below = [record for record in after_checked(done) if n_of(record) % 4 < 3]
    assert below
    for record in below:
        lines = [each.site.line for each in record.forks]
        [own] = forks_at(record, 11)
        assert (own.expression, own.taken) == ([">", QUARTER_TERM, 2], False), record
        assert lines.index(11) < lines.index(16), record


# llm-summary-for-a-call-pyct-cannot-follow-in-use-at-a-watched-call
def test_a_watched_call_in_use_gives_the_later_condition_its_fork() -> None:
    stripped = code_reply('def summary(s):\n    return {"answer": s.strip()}')

    done = summarized(DEDENTED, {"s": "  ab"}, stripped)

    [seed] = before_checked(done)
    assert downgraded(seed, "textwrap.dedent") == [at(63, 8)]
    first = after_checked(done)[0]
    [fork] = forks_at(first, 64)
    assert holds(fork.expression, "s"), first
    assert downgraded(first, "textwrap.dedent") == [], first


# llm-summary-for-a-call-pyct-cannot-follow-in-use-at-a-library-site
def test_a_library_site_in_use_records_no_downgrade_there() -> None:
    spaced = code_reply('def summary(text, arg2):\n    return {"answer": text.replace("\\t", " ")}')

    done = summarized(WRAPPED, {"s": "abcdefg\tb"}, spaced)

    [seed] = before_checked(done)
    [site] = downgraded(seed, "expandtabs")
    assert site.startswith(f"{textwrap.__file__}:")
    assert downgraded(after_checked(done)[0], "expandtabs") == []


# llm-summary-for-a-call-pyct-cannot-follow-in-use-runs-its-input-again
def test_the_input_the_check_used_runs_again_before_the_run_can_stop() -> None:
    done = summarized(SQUARED, {"n": 2}, MOD)

    again = after_checked(done)[0]
    assert (again.args, again.source, again.aim) == ({"n": 2}, Source.SUMMARY, None)
    [fork] = forks_at(again, 30)
    assert fork.expression == ["==", ["%", ["*", "n", "n"], 10], 9]
    assert any(30 + 1 in record.covered_lines for record in done.records)


# llm-summary-for-a-call-pyct-cannot-follow-in-use-runs-its-input-again, where the seed leaves a
# fork to flip: the turn between passes runs it again itself, before any input the solver gives
def test_the_input_the_check_used_runs_again_after_a_turn_between_passes() -> None:
    done = summarized(FORKED, {"n": 2}, MOD)

    again = after_checked(done)[0]
    assert (again.args, again.source, again.aim) == ({"n": 2}, Source.SUMMARY, None)
    [fork] = forks_at(again, 109)
    assert fork.expression == ["==", ["%", ["*", "n", "n"], 10], 9]
    assert done.result.stopped is not None
    assert done.result.stopped.kind is not StopKind.NO_FORK


# llm-summary-for-a-call-pyct-cannot-follow-in-use-state
def test_the_summary_line_says_the_site_s_formula_is_in_use() -> None:
    done = summarized(SHIFTED, {"n": 3}, QUARTER)

    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    [item] = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    assert (item["line"], item["col"]) == (11, 11)
    assert (item["state"], item["checked_on"]) == ("in use", 1)


# llm-summary-for-a-call-pyct-cannot-follow-skipped-in-pyct-s-own-process
def test_inputs_in_pyct_s_own_process_skip_the_site_with_no_ask(stub: Stub, tmp_path: Path) -> None:
    stub.reply = QUARTER

    result = llm_run(
        stub.port, tmp_path, '{"n": 3}', "--llm", "summaries", "--in-process", target=SHIFTED
    )

    assert result.returncode == 0, result.stderr
    assert stub.received == []
    skipped = (
        f"llm: summary for the call __pow__ at {at(11, 11)} skipped:"
        " inputs run in pyct's own process"
    )
    assert llm_lines(result.stderr).count(skipped) == 1
    for line in input_lines(result.stdout):
        downgrades = line["downgrades"]
        assert isinstance(downgrades, list), line
        assert [each["name"] for each in downgrades] == ["__pow__"], line
    llm = summary_line(result.stdout)["llm"]
    assert isinstance(llm, dict)
    assert llm["summaries"] == []


# llm-summary-for-a-call-pyct-cannot-follow-in-use-under-goal-bugs
def test_under_goal_bugs_the_site_is_asked_about_past_full_coverage() -> None:
    bugs = FakeSummaries([QUARTER])

    done = run_summaries(DIVIDED, {"n": 3}, bugs, Limits(plateau=Plateau(20), goal=Goal.BUGS))

    assert places(bugs) == [place(11, 11)]
    assert bugs.inputs_then == [1]
    failed = [record for record in after_checked(done) if record.failure is not None]
    assert failed, done.said
    assert n_of(failed[0]) % 4 == 2
    assert failed[0].source is Source.SUMMARY
    failure = failed[0].failure
    assert failure is not None
    assert "ZeroDivisionError" in failure.detail


# llm-summary-for-a-call-pyct-cannot-follow-in-use-under-goal-bugs, its coverage goal half. The
# seed's input leaves no fork, so the run stops on `no fork to flip`, which the loop names before
# `every line and branch covered` (`pyct.run.loop._attempt`)
def test_under_goal_coverage_the_run_stops_after_the_seed_with_no_ask() -> None:
    coverage = FakeSummaries([QUARTER])

    done = run_summaries(DIVIDED, {"n": 3}, coverage, Limits(plateau=Plateau(20)))

    assert done.result.stopped is not None
    assert done.result.stopped.kind is StopKind.NO_FORK
    assert len(done.records) == 1
    assert coverage.requests == []
