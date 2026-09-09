import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext, _free_tool_id, execute

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


def _load_fixture() -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(FIXTURE.read_text(), str(FIXTURE), "exec"), namespace)
    classify = namespace["classify"]
    assert callable(classify)
    return classify


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
