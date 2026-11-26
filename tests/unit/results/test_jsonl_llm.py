"""The summary line's ``llm`` entry: what the run's LLM tools asked, replayed, skipped, spent and
waited, and each loss site summaries asked about, or null for a run with no ``--llm``."""

import dataclasses
import json

from pyct.results.coverage import Coverage
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse, SiteSummary, SummaryState
from pyct.results.record import InputRecord, RunResult, Stop, StopKind
from tests.unit.environment import ENVIRONMENT

RESULT = RunResult(
    entry="m::f",
    records=(InputRecord(args={"x": 1}, forks=(), covered_lines=frozenset({1})),),
    coverage=Coverage(covered={"m.py": frozenset({1})}, lines={"m.py": frozenset({1})}),
    stopped=Stop(kind=StopKind.NO_FORK),
    environment=ENVIRONMENT,
)


def test_a_run_with_no_llm_writes_null() -> None:
    assert json.loads(render_summary(RESULT))["llm"] is None


# llm-tokens-reported-summary-and-stderr
def test_the_entry_names_the_model_the_tools_and_the_counts() -> None:
    use = LlmUse(
        "openai:gpt-6-luna", ("seeds",), asks=1, tokens_in=1200, tokens_out=300, seconds=12.3
    )

    payload = json.loads(render_summary(RESULT, use))

    assert payload["llm"] == {
        "model": "openai:gpt-6-luna",
        "tools": ["seeds"],
        "asks": 1,
        "replayed": 0,
        "skipped": 0,
        "tokens": {"in": 1200, "out": 300},
        "seconds": 12.3,
        "summaries": [],
    }


def test_the_entry_writes_its_seconds_to_the_millisecond() -> None:
    use = LlmUse("openai:gpt-6-luna", ("seeds",), seconds=0.12345)

    assert json.loads(render_summary(RESULT, use))["llm"]["seconds"] == 0.123


# llm-summary-for-a-call-pyct-cannot-follow-checked-state
def test_the_entry_lists_each_loss_site_summaries_asked_about_with_its_state() -> None:
    formula = 'def summary(n):\n    return {"answer": n}\n'
    answer = ("answer",)
    checked = SiteSummary("__pow__", "m.py", 3, 4, answer, formula, SummaryState.CHECKED, 1, 5)
    failed = SiteSummary("bin", "m.py", 9, 8, answer, None, SummaryState.FAILED, 2)
    unanswered = SiteSummary("f", "m.py", 20, 4, answer, formula, SummaryState.UNANSWERED, 3)
    unchecked = SiteSummary("g", "m.py", 30, 4, answer, formula, SummaryState.UNCHECKED, 1)
    sites = (checked, failed, unanswered, unchecked)
    result = dataclasses.replace(RESULT, summaries=sites)

    payload = json.loads(render_summary(result, LlmUse("openai:gpt-6-luna", ("summaries",))))

    def where(name: str) -> dict[str, object]:
        return {"kind": "call", "name": name, "file": "m.py"}

    assert payload["llm"]["summaries"] == [
        where("__pow__")
        | {"line": 3, "col": 4, "changes": ["answer"], "formula": formula}
        | {"condition": None, "state": "checked", "tries": 1, "checked_on": 5},
        where("bin")
        | {"line": 9, "col": 8, "changes": ["answer"], "formula": None}
        | {"condition": None, "state": "failed", "tries": 2, "checked_on": None},
        where("f")
        | {"line": 20, "col": 4, "changes": ["answer"], "formula": formula}
        | {"condition": None, "state": "unanswered", "tries": 3, "checked_on": None},
        where("g")
        | {"line": 30, "col": 4, "changes": ["answer"], "formula": formula}
        | {"condition": None, "state": "unchecked", "tries": 1, "checked_on": None},
    ]
