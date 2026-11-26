"""Acceptance test for the a-rewrite-reads-an-object-s-fields story's one case about summaries: a
summary formula still reads no attribute, so a field read fails its try before any of it runs."""

import pytest

from pyct.run import summary_checks
from tests.acceptance.llm_summaries import (
    FakeSummaries,
    code_reply,
    one_thread,  # noqa: F401
    run_summaries,
)
from tests.acceptance.lost_calls import SHIFTED


# llm-rewrite-object-fields-refused-leaves-summaries-as-they-are
def test_a_summary_formula_still_reads_no_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_: object) -> object:
        raise AssertionError("a refused formula ran")

    monkeypatch.setattr(summary_checks, "run_model", refused)
    formula = 'def summary(n):\n    return {"answer": n + order.code.count("z")}'
    provider = FakeSummaries([code_reply(formula)])

    done = run_summaries(SHIFTED, {"n": 3}, provider)

    said = [line for line in done.llm_said() if line.startswith("llm: summary for")]
    assert said[0].endswith(", try 1: a formula may not read the attribute code")
