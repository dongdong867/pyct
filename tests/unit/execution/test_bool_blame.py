"""A raise from an operation on a tracked bool: execute reports it as the target's."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda x: 10 // (x > 0), id="division-by-the-bool"),
        pytest.param(lambda x: x % (x > 0), id="int-division-by-the-bool"),
        pytest.param(lambda x: pow(x > 0, 2, 0), id="power-as-the-int"),
        pytest.param(
            lambda x: round(x > 0, 1.5),  # pyrefly: ignore[no-matching-overload]
            id="round-as-the-int",
        ),
        pytest.param(lambda x: format(x > 0, "s"), id="format"),
        pytest.param(lambda x: (x > 0) / 0, id="downgrade"),
    ],
)
def test_execute_reports_a_raise_under_a_bools_own_operation_as_the_targets(
    operation: Callable[[int], object],
) -> None:
    def target(x: int) -> object:
        return operation(x)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"x": 0})

    # the detail is CPython's own sentence, so plain Python on this interpreter gives it
    with pytest.raises((TypeError, ValueError, ZeroDivisionError)) as plain:
        operation(0)
    # a taught operation runs int's own on the 1 or 0 the bool is, and so does a downgrade
    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED,
        detail=f"{type(plain.value).__name__}: {plain.value}",
        traceback=None,
    )
