import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext, _free_tool_id, execute
from pyct.results.failure import Failure, FailureKind

TARGETS = Path(__file__).resolve().parents[3] / "targets" / "trace"
FIXTURE = TARGETS / "uncalled_helper.py"
RAISES = TARGETS / "raises.py"


def _load(file: Path, name: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(file.read_text(), str(file), "exec"), namespace)
    fn = namespace[name]
    assert callable(fn)
    return fn


def _load_fixture() -> Callable[..., object]:
    return _load(FIXTURE, "classify")


def _load_raiser() -> Callable[..., object]:
    return _load(RAISES, "explode")


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
    ctx = ExecutionContext(fn=_load_raiser(), file=str(RAISES))

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
