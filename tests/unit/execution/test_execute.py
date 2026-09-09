import functools
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core import values
from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext, _free_tool_id, execute
from pyct.results.failure import Failure, FailureKind

TARGETS = Path(__file__).resolve().parents[3] / "targets" / "trace"
FIXTURE = TARGETS / "uncalled_helper.py"
RAISES = TARGETS / "raises.py"
NEVER_RETURNS = TARGETS / "never_returns.py"


def _load(file: Path, name: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(file.read_text(), str(file), "exec"), namespace)
    fn = namespace[name]
    assert callable(fn)
    return fn


def _load_fixture() -> Callable[..., object]:
    return _load(FIXTURE, "classify")


def test_execute_returns_the_lines_the_call_ran() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.lines == frozenset({5, 6})


def test_execute_ignores_lines_in_other_files() -> None:
    def elsewhere(x: int) -> int:
        return x + 1

    ctx = ExecutionContext(fn=elsewhere, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.lines == frozenset()


def test_execute_traces_each_call_separately() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    execute(ctx, {"x": 1})
    result = execute(ctx, {"x": 50})

    assert result.lines == frozenset({5, 7})


def test_free_tool_id_takes_an_unassigned_id() -> None:
    if sys.monitoring.get_tool(3) is not None:
        pytest.skip("tool id 3 is already held")

    assert _free_tool_id() == 3


def test_free_tool_id_falls_back_to_a_reserved_id() -> None:
    for tool_id in (3, 4, 0):
        if sys.monitoring.get_tool(tool_id) is not None:
            pytest.skip(f"tool id {tool_id} is already held")
    sys.monitoring.use_tool_id(3, "test")
    sys.monitoring.use_tool_id(4, "test")
    try:
        assert _free_tool_id() == 0
    finally:
        sys.monitoring.free_tool_id(3)
        sys.monitoring.free_tool_id(4)


def test_execute_returns_the_forks_the_call_hit() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.branches == (
        Branch(
            expression=["<", "x", 10],
            taken=True,
            site=Site(file=str(FIXTURE), line=5, col=7),
        ),
    )


def test_execute_records_the_side_the_seed_took() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    result = execute(ctx, {"x": 50})

    assert [branch.taken for branch in result.branches] == [False]


def test_execute_returns_no_forks_when_the_call_takes_none() -> None:
    def straight(x: int) -> int:
        return x

    ctx = ExecutionContext(fn=straight, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.branches == ()


def test_execute_gives_each_call_its_own_sink() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    execute(ctx, {"x": 1})
    result = execute(ctx, {"x": 50})

    assert len(result.branches) == 1


def test_execute_reports_a_raise_as_a_failure_and_keeps_what_ran() -> None:
    def explode(x: int) -> None:
        if x < 10:
            raise ValueError("too small")

    ctx = ExecutionContext(fn=explode, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")
    assert [branch.taken for branch in result.branches] == [True]


def test_execute_reports_no_failure_when_the_call_returns() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure is None
    assert result.downgrades == ()


def test_execute_keeps_the_lines_up_to_the_raise() -> None:
    ctx = ExecutionContext(fn=_load(RAISES, "explode"), file=str(RAISES))

    result = execute(ctx, {"x": 3})

    assert result.lines == frozenset({2, 3})


def test_execute_names_a_raise_in_one_line() -> None:
    def explode(x: int) -> None:
        raise ValueError("first line\nsecond line")

    ctx = ExecutionContext(fn=explode, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure is not None
    assert "\n" not in result.failure.detail
    assert result.failure.detail.startswith("ValueError: first line")


def test_execute_lets_an_interrupt_through() -> None:
    def interrupted(x: int) -> None:
        raise KeyboardInterrupt

    ctx = ExecutionContext(fn=interrupted, file=str(FIXTURE))

    with pytest.raises(KeyboardInterrupt):
        execute(ctx, {"x": 1})


def test_execute_reports_a_system_exit_as_a_failure_and_keeps_going() -> None:
    def leave(x: int) -> None:
        sys.exit(3)

    ctx = ExecutionContext(fn=leave, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure == Failure(kind=FailureKind.SYSTEM_EXIT, detail="SystemExit: 3")


def test_execute_reports_a_timeout_and_keeps_the_lines_it_reached() -> None:
    ctx = ExecutionContext(fn=_load(NEVER_RETURNS, "spin"), file=str(NEVER_RETURNS))

    result = execute(ctx, {"x": 1}, time.monotonic() + 0.05)

    assert result.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert result.lines == frozenset({2, 3, 4})


def test_execute_with_no_deadline_lets_the_call_finish() -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure is None


def test_execute_reports_a_raise_from_pyct_below_the_target_as_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Site:
        raise RuntimeError("boom")

    def compares(x: int) -> bool:
        return bool(x < 10)

    ctx = ExecutionContext(fn=compares, file=str(FIXTURE))
    # the compare reaches this through `ConcolicBool.__bool__`, a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", broken)

    result = execute(ctx, {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail == "RuntimeError: boom"
    assert result.failure.traceback is not None
    assert "compares" in result.failure.traceback


def test_execute_reports_a_raise_from_a_helper_the_target_calls_as_the_targets() -> None:
    def helper(x: int) -> None:
        raise ValueError("too small")

    def calls_helper(x: int) -> None:
        helper(x)

    ctx = ExecutionContext(fn=calls_helper, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")


def test_execute_reports_a_raise_from_a_target_with_no_code_object_as_the_targets() -> None:
    def explode(tag: str, x: int) -> None:
        raise ValueError("too small")

    ctx = ExecutionContext(fn=functools.partial(explode, "tag"), file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: too small")


def test_execute_reports_a_raise_inside_a_downgrade_as_the_targets() -> None:
    def divides(x: int) -> int:
        return x // 0

    ctx = ExecutionContext(fn=divides, file=str(FIXTURE))

    result = execute(ctx, {"x": 1})

    # the downgrade frame only runs int's own `//`, so the raise is the target's
    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED,
        detail="ZeroDivisionError: integer division or modulo by zero",
        traceback=None,
    )


def test_execute_reports_a_downgrade_and_the_fork_it_cost() -> None:
    def through_abs(x: int) -> str:
        y = abs(x)
        return "small" if y < 10 else "big"

    ctx = ExecutionContext(fn=through_abs, file=str(FIXTURE))

    result = execute(ctx, {"x": -3})

    # abs drops the condition, so the compare after it is Python's own and no fork is left
    assert result.downgrades == ("__abs__",)
    assert result.branches == ()


def test_execute_keeps_the_forks_and_the_downgrades_each_in_order() -> None:
    def mixed(x: int) -> int:
        n = 0
        if x < 10:
            n = abs(x)
        if x < 100:
            n = -x
        return n

    ctx = ExecutionContext(fn=mixed, file=str(FIXTURE))

    result = execute(ctx, {"x": 3})

    assert [branch.expression for branch in result.branches] == [
        ["<", "x", 10],
        ["<", "x", 100],
    ]
    assert result.downgrades == ("__abs__", "__neg__")
