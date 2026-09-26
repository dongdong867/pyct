"""A raise from a search on a tracked str: execute reports it as the target's."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


@pytest.mark.parametrize(
    ("operation", "detail"),
    [
        pytest.param(
            lambda s: s.find(5), "TypeError: must be str, not int", id="search-str-refuses"
        ),
        pytest.param(
            lambda s: 5 in s,
            "TypeError: 'in <string>' requires string as left operand, not int",
            id="in-str-refuses",
        ),
        pytest.param(lambda s: s.index("x"), "ValueError: substring not found", id="index-missing"),
    ],
)
def test_execute_reports_a_raise_under_strs_own_operation_as_the_targets(
    operation: Callable[[str], object], detail: str
) -> None:
    def target(s: str) -> object:
        return operation(s)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"s": "abc"})

    # a taught search runs str's own, and so does the downgrade it falls back to
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=detail, traceback=None)


def test_execute_reports_a_keyword_a_search_refuses_as_the_targets() -> None:
    def target(s: str) -> object:
        return s.find("b", start=1)  # pyrefly: ignore[unexpected-keyword]

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"s": "abc"})

    # str's searches take no keywords; the call raises TypeError before anything of pyct runs,
    # so the raise is the target's though its words are Python's for pyct's method, not str's
    assert result.failure is not None
    assert result.failure.kind == FailureKind.TARGET_RAISED
    assert result.failure.detail.startswith("TypeError:")
    assert "unexpected keyword argument 'start'" in result.failure.detail
