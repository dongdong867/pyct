"""The summary line's ``llm`` entry: what the run's LLM tools asked, replayed, skipped, spent and
waited, or null for a run with no ``--llm``."""

import json

from pyct.results.coverage import Coverage
from pyct.results.jsonl import render_summary
from pyct.results.llm_asks import LlmUse
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
    }


def test_the_entry_writes_its_seconds_to_the_millisecond() -> None:
    use = LlmUse("openai:gpt-6-luna", ("seeds",), seconds=0.12345)

    assert json.loads(render_summary(RESULT, use))["llm"]["seconds"] == 0.123
