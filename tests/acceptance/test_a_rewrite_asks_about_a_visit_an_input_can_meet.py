"""Acceptance tests for the a-rewrite-asks-about-a-visit-an-input-can-meet ticket: when a condition
the solver gives up on sits in a loop, pyct asks about the condition's first kept plan, whose path
does not already hold the same check on the other side, solves the rewrite alone, and the
rewrite's input covers the line.

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


# `pick(s)`: `for word in ["2", "1"]:` on line 2, `if s.startswith(word) and float(s) == 1e-30:` on
# line 3 guards `return word` on line 4
PICK = "targets.rewrites.later_visit::pick"
AT_PICK = f"llm: rewrite for {file_of('later_visit')}:3:34"


# llm-rewrite-visit-an-input-can-meet-covers-a-line-only-the-second-visit-reaches
def test_a_rewrite_solved_alone_covers_a_line_only_the_second_visit_reaches() -> None:
    provider = FakeRewrites([WANTED])

    ran = run_rewrites(PICK, {"s": "2"}, provider, LOOPED)

    # one try: asked about the first visit, the expression solved alone gives an input that
    # takes the wanted side on the second
    [request] = provider.requests
    assert request.args == (("s", '"2"'),)
    assert llm_said(ran.said) == [f"{AT_PICK}: {WANTED}", f"{AT_PICK}: took the wanted side"]
    found = [record for record in ran.records if 4 in record.covered_lines]
    assert found[0].source is Source.REWRITE
    assert found[0].args == {"s": "1e-30"}
