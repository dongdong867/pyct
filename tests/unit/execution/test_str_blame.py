"""A raise from a search, a piece, a check, a change or a split of a tracked str: execute
reports it as the target's."""

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
        pytest.param(lambda s: s[5], id="index-past-the-end"),
        pytest.param(lambda s: s["a"], id="index-str-refuses"),
        pytest.param(lambda s: s + 1, id="plus-str-refuses"),
        pytest.param(lambda s: s.replace(1, "x"), id="replace-str-refuses"),
        pytest.param(
            lambda s: s.isdigit(1),  # pyrefly: ignore[bad-argument-count]
            id="check-str-refuses",
        ),
        pytest.param(lambda s: s.center(9, "**"), id="padding-fill-refused"),
        pytest.param(lambda s: s.split(""), id="split-empty-separator"),
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
    with pytest.raises((TypeError, ValueError, IndexError)) as plain:
        operation("abc")
    # a taught search or piece runs str's own, and so does the downgrade it falls back to
    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED,
        detail=f"{type(plain.value).__name__}: {plain.value}",
        traceback=None,
    )
