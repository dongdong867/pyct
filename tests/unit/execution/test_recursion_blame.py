"""A RecursionError is the target's when its own recursion filled the stack, wherever the limit
was hit, and pyct's frames below the target do not count against the target's depth."""

import sys
from collections.abc import Callable

import pytest

from pyct.core import values
from pyct.core.branch import PYCT_DIR
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import FailureKind


def _plain_recursion_error() -> str:
    """What plain Python says when a recursion without end passes the limit, in this run."""

    def down(n: int) -> int:
        return down(n - 1)

    try:
        down(0)
    except RecursionError as error:
        return f"{type(error).__name__}: {error}"
    raise AssertionError("the recursion ended")  # pragma: no cover


def _deep(n: int) -> int:
    # the compare forks on every level, so pyct's frames sit on top of the target's each time
    if n <= 0:
        return 0
    return 1 + _deep(n - 1)


def _in_pyct(source: str, name: str) -> Callable[..., object]:
    """A function whose code lives under pyct's directory, as pyct's own frames do."""
    namespace: dict[str, object] = {}
    exec(compile(source, f"{PYCT_DIR}/recursing.py", "exec"), namespace)
    fn = namespace[name]
    assert callable(fn)
    return fn


def test_a_recursion_without_end_in_the_target_is_the_target_s() -> None:
    expected = _plain_recursion_error()
    ctx = ExecutionContext(fn=_deep, file=__file__)

    result = execute(ctx, {"n": 100_000})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED, result.failure.traceback
    assert result.failure.detail == expected


def test_a_recursion_without_end_in_pyct_s_own_frames_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _in_pyct("def broken():\n    return broken()\n", "broken")

    def compares(x: int) -> bool:
        return bool(x < 10)

    # the compare reaches this through `ConcolicBool.__bool__`, a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", broken)

    result = execute(ExecutionContext(fn=compares, file=__file__), {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail.startswith("RecursionError")
    assert result.failure.traceback is not None


def test_the_target_recurses_as_deep_as_from_a_module_s_top_level() -> None:
    # the frames below this test's call, pytest's and execute's, take none of the target's depth;
    # 30 frames are left for pyct's own above the deepest, as a fork puts there
    depth = sys.getrecursionlimit() - 30
    ctx = ExecutionContext(fn=_deep, file=__file__)

    result = execute(ctx, {"n": depth})

    assert result.failure is None, result.failure


def test_the_recursion_limit_comes_back_after_the_call() -> None:
    before = sys.getrecursionlimit()

    execute(ExecutionContext(fn=_deep, file=__file__), {"n": 3})

    assert sys.getrecursionlimit() == before


def test_a_limit_the_target_sets_stays_the_target_s() -> None:
    before = sys.getrecursionlimit()

    def sets(x: int) -> int:
        sys.setrecursionlimit(before + 777)
        return x

    try:
        execute(ExecutionContext(fn=sets, file=__file__), {"x": 3})
        assert sys.getrecursionlimit() == before + 777
    finally:
        sys.setrecursionlimit(before)


def test_a_runaway_in_pyct_s_frames_on_top_of_a_deep_target_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _in_pyct("def broken():\n    return broken()\n", "broken")

    def runaway_on_top(x: int) -> bool:
        def down(depth: int) -> bool:
            if depth == 0:
                return bool(x < 10)
            return down(depth - 1)

        # the target's own frames take most of the stack, and pyct runs away in what is left
        return down(sys.getrecursionlimit() - 150)

    monkeypatch.setattr(values, "caller_site", broken)

    result = execute(ExecutionContext(fn=runaway_on_top, file=__file__), {"x": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail.startswith("RecursionError")


def test_a_target_that_recurses_through_a_pyct_frame_at_every_level_is_the_target_s() -> None:
    through = _in_pyct("def through(f, n):\n    return f(n)\n", "through")

    def again(n: int) -> object:
        return through(again, n + 1)

    result = execute(ExecutionContext(fn=again, file=__file__), {"n": 0})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED, result.failure.traceback
    assert result.failure.detail == _plain_recursion_error()
