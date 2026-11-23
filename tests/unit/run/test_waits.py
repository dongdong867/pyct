"""Whether a pick's site waits for the last picks, after each answer and its seconds."""

import pytest

from pyct.run.waits import site_waits
from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat


# a-slow-unknown-waits-for-the-last-picks-at-a-quarter-of-the-limit
@pytest.mark.parametrize(
    ("answer", "seconds", "waits"),
    [
        (Unknown(), 2.49, False),
        (Unknown(), 2.5, True),
        (Unknown(), 10.0, True),
        (Unknown(guarded=True), 2.49, False),
        (Unknown(guarded=True), 2.5, True),
        (Timeout(), 0.0, True),
        (Sat({}), 10.0, False),
        (Unsat(), 10.0, False),
    ],
    ids=[
        "unknown-under-a-quarter",
        "unknown-at-a-quarter",
        "unknown-at-the-limit",
        "guarded-unknown-under-a-quarter",
        "guarded-unknown-at-a-quarter",
        "timeout",
        "sat",
        "unsat",
    ],
)
def test_a_site_waits_after_a_timeout_or_an_unknown_that_used_a_quarter_of_its_limit(
    answer: Answer, seconds: float, waits: bool
) -> None:
    assert site_waits(answer, seconds, 10.0) is waits
