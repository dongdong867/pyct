"""Acceptance tests for the track-a-value-through-a-call-summary story's drops through ``run()``: a
loss site's formula in use is checked on every run of the site, the first input it fails on drops
it, and pyct asks about the site again at the next turn, with the dropped formula and the run it
failed on.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs, and each input in a forked child; no test calls a model.
"""

import json
import re

from pyct.config.goal import Goal
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.results.record import InputRecord
from tests.acceptance.llm_summaries import (
    TOKENS,
    FakeSummaries,
    Summarized,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import (
    BOUNDED,
    EACH_DEDENTED,
    MOD,
    WRONG,
    WRONG_CODE,
    at,
    place,
)
from tests.acceptance.test_track_a_value_through_a_call_summary import (
    LONGER,
    after_checked,
    downgraded,
    n_of,
)

# the site of `pow(n, 2, 10)` in `bounded`, as stderr writes it
POW = at(84, 8)
DROPPED = re.compile(
    rf"llm: summary for the call __pow__ at {re.escape(POW)} dropped at input (\d+):"
    r" answer was (-?\d+), the formula gave (-?\d+)"
)


def dropped(done: Summarized) -> list[tuple[int, int, int]]:
    """Each ``dropped at input`` line about the site, as its input's number, A and G."""
    found = [DROPPED.fullmatch(line) for line in done.llm_said()]
    return [(int(m[1]), int(m[2]), int(m[3])) for m in found if m is not None]


def state_of(done: Summarized) -> object:
    use = LlmUse("openai:gpt-6-luna", ("summaries",))
    [item] = json.loads(render_summary(done.result, use))["llm"]["summaries"]
    return item["state"]


def squared_past(record: InputRecord) -> bool:
    return n_of(record) * n_of(record) >= 10


# llm-summary-for-a-call-pyct-cannot-follow-dropped-at-the-first-mismatch
def test_the_first_input_the_formula_fails_on_drops_it() -> None:
    provider = FakeSummaries([WRONG], limit=sum(TOKENS))

    done = run_summaries(BOUNDED, {"n": 2}, provider, LONGER)

    after = after_checked(done)
    first = next(record for record in after if squared_past(record))
    number = done.records.index(first) + 1
    n = n_of(first)
    assert dropped(done) == [(number, n * n % 10, n * n)]
    assert downgraded(first, "__pow__") == [POW]
    for record in after[: after.index(first)]:
        assert downgraded(record, "__pow__") == [], record
    assert state_of(done) == "dropped"


# llm-summary-for-a-call-pyct-cannot-follow-asked-again-after-a-drop
def test_a_dropped_site_is_asked_about_again_at_the_next_turn() -> None:
    provider = FakeSummaries([WRONG, MOD])

    done = run_summaries(BOUNDED, {"n": 2}, provider, LONGER)

    [(number, answer, got)] = dropped(done)
    assert [request.place for request in provider.requests] == [place(84, 8)] * 2
    assert provider.inputs_then[1] == number
    assert provider.tries[place(84, 8)] == 2
    again = provider.requests[1]
    reason = f"dropped at input {number}: answer was {answer}, the formula gave {got}"
    assert [(each.formula, each.reason) for each in again.tries] == [(f"{WRONG_CODE}\n", reason)]
    n = done.records[number - 1].args["n"]
    assert again.runs[0].going_in == (("n", json.dumps(n)),)
    said = done.llm_said()
    read = f"llm: summary for the call __pow__ at {POW}: answer = n * n % 10"
    dropped_at = next(at for at, line in enumerate(said) if DROPPED.fullmatch(line))
    assert said.index(read) > dropped_at
    assert any(": checked on " in line for line in said[said.index(read) :])
    assert state_of(done) == "in use"


# the site of `textwrap.dedent(s)` in `each_dedented`, and a formula for it that holds on the first
# three items of `TEXTS`, the runs the input records, and one that holds there too but not on the
# fourth
DEDENT = place(100, 11)
LSTRIP = code_reply('def summary(s):\n    return {"answer": s.lstrip()}')
STRIP = code_reply('def summary(s):\n    return {"answer": s.strip()}')
TEXTS = [" a", " b", " c", " d\n e"]


# llm-summary-for-a-call-pyct-cannot-follow-asked-again-after-a-drop, at a watched call's fourth
# start in one input, past the runs the input records
def test_a_watched_call_dropped_past_its_recorded_runs_is_asked_about_with_that_run_first() -> None:
    provider = FakeSummaries([LSTRIP, STRIP])
    limits = Limits(plateau=Plateau(20), goal=Goal.BUGS)

    done = run_summaries(EACH_DEDENTED, {"texts": TEXTS}, provider, limits)

    assert [request.place for request in provider.requests] == [DEDENT] * 2
    again = provider.requests[1]
    [earlier] = again.tries
    found = re.fullmatch(r"dropped at input (\d+): .*", earlier.reason, re.S)
    assert found is not None
    number = int(found[1])
    assert again.runs[0].going_in == (("s", json.dumps(" d\n e")),)
    refused = f'at input {number}, answer was "d\\ne", the formula gave "d\\n e"'
    at_dedent = f"llm: summary for the call textwrap.dedent at {at(100, 11)}"
    assert f"{at_dedent}, try 2: {refused}" in done.llm_said()
