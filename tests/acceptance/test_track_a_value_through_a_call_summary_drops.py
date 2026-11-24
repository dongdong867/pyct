"""Acceptance tests for the track-a-value-through-a-call-summary story's drops through ``run()``: a
loss site's formula in use is checked on every run of the site, the first input it fails on drops
it, and pyct asks about the site again at the next turn, with the dropped formula and the run it
failed on.

Each run has summaries on with a fake provider, its package intercepted with the recording of
each loop's runs, and each input in a forked child; no test calls a model.
"""

import json
import re

from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
from pyct.results.record import InputRecord
from tests.acceptance.llm_summaries import (
    TOKENS,
    FakeSummaries,
    Summarized,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import BOUNDED, WRONG, at
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
