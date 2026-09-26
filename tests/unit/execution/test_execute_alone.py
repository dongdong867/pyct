"""A call alone in its process: every raise that is not a deadline or an exit is a failure."""

import pytest

from pyct.core import values
from pyct.core.branch import Site
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import Failure, FailureKind


class Halt(BaseException):
    """A raise of the target's own that is neither an Exception nor SystemExit."""


def interrupts(x: int) -> None:
    if x > 3:
        raise KeyboardInterrupt


def halts(x: int) -> None:
    raise Halt("halted")


def test_a_keyboard_interrupt_the_target_raises_is_its_raise() -> None:
    ctx = ExecutionContext(fn=interrupts, file=__file__, alone=True)

    result = execute(ctx, {"x": 5})

    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="KeyboardInterrupt")
    # what the call did before the raise stays
    assert [branch.taken for branch in result.branches] == [True]


def test_a_base_exception_of_the_targets_own_is_its_raise() -> None:
    ctx = ExecutionContext(fn=halts, file=__file__, alone=True)

    result = execute(ctx, {"x": 5})

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail=f"{__name__}.Halt: halted"
    )


def test_a_base_exception_out_of_pyct_below_the_target_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Site:
        raise Halt("pyct's own")

    def compares(x: int) -> bool:
        return bool(x < 10)

    # the compare reaches this through `ConcolicBool.__bool__`, a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", broken)
    ctx = ExecutionContext(fn=compares, file=__file__, alone=True)

    result = execute(ctx, {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.traceback is not None


def test_a_call_in_pyct_s_own_process_lets_a_keyboard_interrupt_through() -> None:
    ctx = ExecutionContext(fn=interrupts, file=__file__)

    with pytest.raises(KeyboardInterrupt):
        execute(ctx, {"x": 5})
