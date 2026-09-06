from collections.abc import Callable
from pathlib import Path

from pyct.execution.execute import ExecutionContext, execute

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
