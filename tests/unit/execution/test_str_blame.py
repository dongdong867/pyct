"""A raise from a search on a tracked str: execute reports it as the target's."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda s: s.find(5), id="search-str-refuses"),
        pytest.param(lambda s: 5 in s, id="in-str-refuses"),
        pytest.param(lambda s: s.index("x"), id="index-missing"),
        pytest.param(
            lambda s: s.find("b", start=1),  # pyrefly: ignore[unexpected-keyword]
            id="search-keyword-refused",
        ),
    ],
)
def test_execute_reports_a_raise_under_strs_own_operation_as_the_targets(
    operation: Callable[[str], object],
) -> None:
    def target(s: str) -> object:
        return operation(s)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"s": "abc"})

    # the detail is CPython's own sentence, so plain Python on this interpreter gives it
    with pytest.raises((TypeError, ValueError)) as plain:
        operation("abc")
    # a taught search runs str's own, and so does the downgrade it falls back to
    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED,
        detail=f"{type(plain.value).__name__}: {plain.value}",
        traceback=None,
    )
