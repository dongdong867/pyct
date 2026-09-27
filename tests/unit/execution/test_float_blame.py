"""A raise from an operation on a tracked float: execute reports it as the target's."""

import math
from collections.abc import Callable

import pytest

from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind
from tests.unit.execution.test_str_blame import FIXTURE


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda x: x / 0.0, id="taught-division-by-zero"),
        pytest.param(lambda x: 1.0 / (x - x), id="taught-reflected-division-by-zero"),
        pytest.param(
            lambda x: x.is_integer(1),  # pyrefly: ignore[bad-argument-count]
            id="taught-is-integer-refuses",
        ),
        pytest.param(lambda x: int(x * math.inf * 0.0), id="downgrade-int-of-nan"),
        pytest.param(lambda x: x // 0, id="downgrade-floor-division-by-zero"),
    ],
)
def test_execute_reports_a_raise_under_floats_own_operation_as_the_targets(
    operation: Callable[[float], object],
) -> None:
    def target(x: float) -> object:
        return operation(x)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"x": 1.5})

    # the detail is CPython's own sentence, so plain Python on this interpreter gives it
    with pytest.raises((TypeError, ValueError, ZeroDivisionError)) as plain:
        operation(1.5)
    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED,
        detail=f"{type(plain.value).__name__}: {plain.value}",
        traceback=None,
    )
