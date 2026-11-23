"""Acceptance test for the a-rewrite-s-ask-keeps-a-fact-the-model-never-sees ticket: once the
solver could not answer a rewrite's ask, the next ask asks for a condition that fixes each
parameter it reads to one exact value, and such a rewrite's input covers the line.

It runs ``run()`` with a fake ``RewriteProvider`` that answers fixed text.
"""

from pyct.llm.rewrites import EXACT_VALUE, request_text
from pyct.results.record import Source
from tests.acceptance.llm_rewrites import (
    SHORT,
    FakeRewrites,
    file_of,
    llm_said,
    one_thread,  # noqa: F401
    run_rewrites,
)

# `big(s)`: `if s.isdigit() and int(s) > 10**30:` on line 2 guards `return 1` on line 3
DIGITS = "targets.rewrites.digits::big"
AT = f"llm: rewrite for {file_of('digits')}:2:23"


# llm-rewrite-retry-asks-for-one-exact-value-covers-the-line
def test_a_retry_after_the_solver_gave_up_asks_for_one_exact_value_and_covers_the_line() -> None:
    provider = FakeRewrites(["len(s) > 31", "s == str(10**30 + 1)"])

    ran = run_rewrites(DIGITS, {"s": "5"}, provider, SHORT)

    # cvc5 may say unknown rather than timeout as it reaches its time limit
    [failed] = [line for line in llm_said(ran.said) if line.startswith(f"{AT}, try ")]
    assert failed in (
        f"{AT}, try 1: the solver answered timeout",
        f"{AT}, try 1: the solver answered unknown",
    )
    first, second = provider.requests
    assert EXACT_VALUE not in request_text(first)
    assert EXACT_VALUE in request_text(second)
    [line_3] = [record for record in ran.records if 3 in record.covered_lines]
    assert line_3.source is Source.REWRITE
    assert line_3.args == {"s": str(10**30 + 1)}
