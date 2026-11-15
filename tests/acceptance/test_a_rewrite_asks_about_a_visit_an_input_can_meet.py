"""Acceptance test for the a-rewrite-asks-about-a-visit-an-input-can-meet ticket: when a condition
the solver gives up on sits in a loop, pyct asks about a visit whose path does not already hold
the same check on the other side, and the rewrite's input covers the line.

It runs ``run()`` with a fake ``RewriteProvider`` that answers fixed text.
"""

import dataclasses

from pyct.config.budget import Budget
from pyct.results.record import Source
from tests.acceptance.llm_rewrites import (
    SHORT,
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)

# `each(s, items)`: `for x in items:` on line 2, `if x > 0 and float(s) == 1e-30:` on line 3
# guards `return x` on line 4
EACH = "targets.rewrites.visits::each"
AT = f"llm: rewrite for {file_of('visits')}:3:21"
WANTED = 's == "1e-30"'
# SHORT's solver limit, with a budget: the loop takes a longer list on each input, so a run that
# covers no line 4 ends at its budget
LOOPED = dataclasses.replace(SHORT, budget=Budget(30))


# llm-rewrite-visit-an-input-can-meet-covers-the-loop-s-line
def test_a_rewrite_for_a_check_in_a_loop_covers_its_line() -> None:
    provider = FakeRewrites([WANTED])

    ran = run_rewrites(EACH, {"s": "0", "items": [1, 2, 3]}, provider, LOOPED)

    assert llm_said(ran.said)[:2] == [f"{AT}: {WANTED}", f"{AT}: took the wanted side"]
    request = provider.requests[0]
    assert request.condition.text == "float(s) == 1e-30"
    assert "float(s) == 1e-30" not in [each.text for each in request.earlier]
    [line_4] = [record for record in ran.records if 4 in record.covered_lines]
    assert line_4.source is Source.REWRITE
    assert line_4.args["s"] == "1e-30"
