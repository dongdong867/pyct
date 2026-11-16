"""Acceptance tests for the track-a-value-through-a-loop-summary story's
``llm-summary-checked-on-every-run`` criteria through ``run()``: a formula in use is checked on
each input's run of its loop, dropped at the first it misses, and the loop is followed as before.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs, and each input in a forked child; no test calls a model.
"""

import json
import re
from pathlib import Path

from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.results.record import InputRecord
from pyct.run.summaries import EarlierFormula
from pyct.run.summary_runs import ShownRun
from tests.acceptance.llm_summaries import (
    COUNT,
    SEED,
    TOKENS,
    FakeSummaries,
    G,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.test_substitute_is_and_in import plain_lines
from tests.acceptance.test_track_a_value_through_a_loop_summary import (
    CAPPED,
    LOOPS,
    Z,
    after_checked,
    forks_at,
    holds,
    line_of,
)

# a run that goes on well past its first moment
LONGER = Limits(plateau=Plateau(20))
# `COUNT` with a count past 3 dividing by zero: it holds on every run before the moment
RAISES = code_reply(
    'def summary(s, t):\n    t = t + s.count("z")\n    if t > 3:\n        t = 1 // 0\n'
    '    return {"t": t}'
)


def dropped_run() -> Summarized:
    """``capped`` run from the seed, the provider answering ``COUNT``. The run's token limit
    allows that one reply, so no later moment asks about the loop again and the run ends as the
    drop left it."""
    provider = FakeSummaries([COUNT], limit=sum(TOKENS))
    done = run_summaries(f"{LOOPS}::capped", SEED, provider, LONGER)
    assert len(provider.requests) == 1
    return done


def items(done: Summarized) -> list[dict[str, object]]:
    """Each loop's item in the summary line's ``llm.summaries``."""
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    return json.loads(render_summary(done.result, use))["llm"]["summaries"]


def first_dropped(done: Summarized) -> int:
    """The number, from 1, of the first input whose record carries a drop."""
    return next(number for number, record in enumerate(done.records, 1) if record.drops)


def after_said(done: Summarized, said: str) -> list[InputRecord]:
    """The inputs that ran after the line ``said``."""
    at = done.said.index(said)
    return done.records[sum(1 for line in done.said[:at] if line.startswith("input ")) :]


def dropped_line(function: str, number: int, reason: str) -> str:
    loop = line_of(function, "for c in s:")
    return f"llm: summary for the loop at {G}:{loop} dropped at input {number}: {reason}"


# llm-summary-checked-on-every-run-dropped-at-the-first-mismatch
def test_the_first_input_the_formula_misses_drops_it() -> None:
    done = dropped_run()

    after = after_checked(done)
    before = len(done.records) - len(after)
    over_five = [at for at, each in enumerate(after) if str(each.args["s"]).count("z") > 5]
    assert over_five, [each.args for each in after]
    number = before + over_five[0] + 1
    record = done.records[number - 1]
    s = str(record.args["s"])
    reason = f"t was 5, the formula gave {s.count('z')}"
    assert dropped_line("capped", number, reason) in done.llm_said()
    assert first_dropped(done) == number
    assert sorted(record.covered_lines) == plain_lines(Path(G), "capped", s)
    assert line_of("capped", 'return "few"') in record.covered_lines
    assert forks_at(record, line_of("capped", "if t > 5:")) == []


# llm-summary-checked-on-every-run-followed-as-before-after-a-drop
def test_an_input_after_the_drop_follows_the_loop_as_before() -> None:
    done = dropped_run()

    number = first_dropped(done)
    s = str(done.records[number - 1].args["s"])
    reason = f"t was 5, the formula gave {s.count('z')}"
    after = after_said(done, dropped_line("capped", number, reason))
    assert after
    test = line_of("capped", 'if c == "z" and t < 5:')
    for record in after:
        read = str(record.args["s"])
        assert len(forks_at(record, test)) == len(read), record
        assert not any(holds(each.expression, Z) for each in record.forks), record


# llm-summary-checked-on-every-run-earlier-inputs-keep-their-lines
def test_an_input_before_the_drop_keeps_its_lines() -> None:
    done = dropped_run()

    four = line_of("capped", 'return "four"')
    number = first_dropped(done)
    fours = [
        at
        for at, record in enumerate(done.records[: number - 1])
        if str(record.args["s"]).count("z") == 4 and four in record.covered_lines
    ]
    assert fours, [record.args for record in done.records]
    # each input's line is printed once, as it finished, and the run keeps that input as it was
    assert done.said.count(f"input {fours[0] + 1}") == 1
    assert done.result.records[fours[0]] == done.records[fours[0]]
    assert four in done.result.coverage.covered[G]


# llm-summary-checked-on-every-run-dropped-state
def test_a_dropped_formula_is_listed_dropped_with_its_check() -> None:
    done = dropped_run()

    checked = next(line for line in done.said if ": checked on " in line)
    found = re.search(r"checked on (\d+) past runs", checked)
    assert found is not None
    [item] = items(done)
    assert item["state"] == "dropped"
    assert item["formula"] == first_formula()
    assert item["tries"] == 1
    assert item["checked_on"] == int(found.group(1))


# llm-summary-checked-on-every-run-formula-raises
def test_a_formula_that_raises_is_dropped_and_the_input_runs_as_plain_python() -> None:
    provider = FakeSummaries([RAISES])

    done = run_summaries(f"{LOOPS}::few_z", SEED, provider, LONGER)

    before = len(done.records) - len(after_checked(done))
    many = [
        number
        for number, record in enumerate(done.records, 1)
        if number > before and str(record.args["s"]).count("z") >= 4
    ]
    assert many, [record.args for record in done.records]
    raised = "the formula raised ZeroDivisionError"
    assert dropped_line("few_z", many[0], raised) in done.llm_said()
    record = done.records[many[0] - 1]
    assert line_of("few_z", 'return "many"') in record.covered_lines
    assert sorted(record.covered_lines) == plain_lines(Path(G), "few_z", str(record.args["s"]))


# llm-summary-checked-on-every-run-asked-again-after-a-drop
def test_a_dropped_loop_is_asked_about_again_with_why_and_the_run_it_failed_on() -> None:
    provider = FakeSummaries([COUNT, CAPPED])

    done = run_summaries(f"{LOOPS}::capped", SEED, provider, LONGER)

    assert len(provider.requests) == 2
    number = first_dropped(done)
    s = str(done.records[number - 1].args["s"])
    reason = f"t was 5, the formula gave {s.count('z')}"
    first, again = provider.requests
    assert again.place == first.place
    assert again.tries == (EarlierFormula(first_formula(), f"dropped at input {number}: {reason}"),)
    # the run the formula failed on comes first among the runs
    assert again.runs[0] == ShownRun((("s", json.dumps(s)), ("t", "0")), (("t", "5"),))
    assert provider.tries[again.place] == 2
    said = done.llm_said()
    at = said.index(dropped_line("capped", number, reason))
    loop = f"llm: summary for the loop at {G}:{line_of('capped', 'for c in s:')}"
    assert said[at + 1] == (
        f'{loop}:\n    t = t + s.count("z")\n    if t > 5:\n        t = 5\n    return {{"t": t}}'
    )
    assert re.fullmatch(rf"{re.escape(loop)}: checked on \d+ past runs", said[at + 2])
    [item] = items(done)
    assert (item["state"], item["tries"]) == ("in use", 2)


def first_formula() -> str:
    """The code block of ``COUNT``, as the reply holds it."""
    return 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'
