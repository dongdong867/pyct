import bisect
import functools
import math
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core import values
from pyct.core.branch import Branch, Site
from pyct.execution.execute import ExecutionContext, _free_tool_id, execute
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount

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


def _overflow_on_arming(which: int, seconds: float) -> None:
    """A setitimer that fails only the arming; the cancel is setitimer(..., 0) and must run."""
    if seconds:
        raise OverflowError("timestamp out of range for platform time_t")


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


@pytest.mark.parametrize(
    ("operation", "detail"),
    [
        pytest.param(lambda x: x / 0, "ZeroDivisionError: division by zero", id="downgrade"),
        pytest.param(
            lambda x: x // 0,
            "ZeroDivisionError: integer division or modulo by zero",
            id="division",
        ),
        pytest.param(
            lambda x: divmod(x, 0),
            "ZeroDivisionError: integer division or modulo by zero",
            id="divmod",
        ),
        pytest.param(
            lambda x: x**-1,
            "ZeroDivisionError: 0.0 cannot be raised to a negative power",
            id="power",
        ),
        pytest.param(
            lambda x: pow(x, 2, 0), "ValueError: pow() 3rd argument cannot be 0", id="modular-power"
        ),
        pytest.param(
            lambda x: round(x, 1.5),  # pyrefly: ignore[no-matching-overload]
            "TypeError: 'float' object cannot be interpreted as an integer",
            id="round",
        ),
    ],
)
def test_execute_reports_a_raise_under_ints_own_operation_as_the_targets(
    operation: Callable[[int], object], detail: str
) -> None:
    def target(x: int) -> object:
        return operation(x)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"x": 0})

    # a downgrade, and a taught operation's fallback, only run int's own; the raise is the target's
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=detail, traceback=None)


@pytest.mark.parametrize(
    ("operation", "detail"),
    [
        pytest.param(
            lambda s: s.find(5), "TypeError: must be str, not int", id="search-str-refuses"
        ),
        pytest.param(
            lambda s: 5 in s,
            "TypeError: 'in <string>' requires string as left operand, not int",
            id="in-str-refuses",
        ),
        pytest.param(lambda s: s.index("x"), "ValueError: substring not found", id="index-missing"),
    ],
)
def test_execute_reports_a_raise_under_strs_own_operation_as_the_targets(
    operation: Callable[[str], object], detail: str
) -> None:
    def target(s: str) -> object:
        return operation(s)

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"s": "abc"})

    # a taught search runs str's own, and so does the downgrade it falls back to
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=detail, traceback=None)


def test_execute_reports_a_keyword_a_search_refuses_as_the_targets() -> None:
    def target(s: str) -> object:
        return s.find("b", start=1)  # pyrefly: ignore[unexpected-keyword]

    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"s": "abc"})

    # str's searches take no keywords; the call raises TypeError before anything of pyct runs,
    # so the raise is the target's though its words are Python's for pyct's method, not str's
    assert result.failure is not None
    assert result.failure.kind == FailureKind.TARGET_RAISED
    assert result.failure.detail.startswith("TypeError:")
    assert "unexpected keyword argument 'start'" in result.failure.detail


def _raises_it(v: int | str) -> None:
    raise ValueError(v)


def _exits_with_it(v: int | str) -> None:
    sys.exit(v)


@pytest.mark.parametrize(
    ("target", "value", "failure"),
    [
        pytest.param(
            _raises_it,
            "abc",
            Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: abc"),
            id="raise-str",
        ),
        pytest.param(
            _raises_it,
            3,
            Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: 3"),
            id="raise-int",
        ),
        pytest.param(
            _exits_with_it,
            "abc",
            Failure(kind=FailureKind.SYSTEM_EXIT, detail="SystemExit: abc"),
            id="exit-str",
        ),
    ],
)
def test_execute_reads_the_sink_before_it_writes_the_failure(
    target: Callable[[int | str], None], value: int | str, failure: Failure
) -> None:
    ctx = ExecutionContext(fn=target, file=str(FIXTURE))

    result = execute(ctx, {"v": value})

    # writing the failure asks the tracked value for its text; that call is pyct's, not the
    # target's, so it is not a downgrade
    assert result.failure == failure
    assert result.downgrades == ()


def _downgrades_then_raises(v: str) -> None:
    v.upper()
    raise ValueError(v)


def test_execute_keeps_the_targets_downgrades_when_it_raises() -> None:
    ctx = ExecutionContext(fn=_downgrades_then_raises, file=str(FIXTURE))

    result = execute(ctx, {"v": "abc"})

    # the target's own downgrade before the raise stays; writing the failure adds none
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail="ValueError: abc")
    assert result.downgrades == (DowngradeCount(name="upper", count=1),)


def test_execute_reports_a_downgrade_and_the_fork_it_cost() -> None:
    def through_shift(x: int) -> str:
        y = x >> 1
        return "small" if y < 10 else "big"

    ctx = ExecutionContext(fn=through_shift, file=str(FIXTURE))

    result = execute(ctx, {"x": -3})

    # a shift drops the condition, so the compare after it is Python's own and no fork is left
    assert result.downgrades == (DowngradeCount(name="__rshift__", count=1),)
    assert result.branches == ()


def test_execute_keeps_the_forks_and_the_downgrades_each_in_order() -> None:
    def mixed(x: int) -> int:
        n = 0
        if x < 10:
            n = x >> 1
        if x < 100:
            n = ~x
        return n

    ctx = ExecutionContext(fn=mixed, file=str(FIXTURE))

    result = execute(ctx, {"x": 3})

    assert [branch.expression for branch in result.branches] == [
        ["<", "x", 10],
        ["<", "x", 100],
    ]
    assert result.downgrades == (
        DowngradeCount(name="__rshift__", count=1),
        DowngradeCount(name="__invert__", count=1),
    )


def test_execute_collapses_a_run_of_one_downgraded_call_into_one_count() -> None:
    def repeats(x: int) -> int:
        x >> 1
        x >> 1
        y = x | 1
        x >> 1
        return y

    ctx = ExecutionContext(fn=repeats, file=str(FIXTURE))

    result = execute(ctx, {"x": 3})

    # only calls next to each other collapse, so the second run of shifts is its own entry
    assert result.downgrades == (
        DowngradeCount(name="__rshift__", count=2),
        DowngradeCount(name="__or__", count=1),
        DowngradeCount(name="__rshift__", count=1),
    )


def test_execute_reports_a_raise_before_the_target_ran_as_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = ExecutionContext(fn=_load_fixture(), file=str(FIXTURE))
    before = signal.getsignal(signal.SIGALRM)
    # the timer is armed before the target is called, so the traceback has no frame of its own
    monkeypatch.setattr(signal, "setitimer", _overflow_on_arming)

    result = execute(ctx, {"x": 1}, time.monotonic() + 1)

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.traceback is not None
    # the cancel on the way out ran, so the handler pyct installed is gone again
    assert signal.getsignal(signal.SIGALRM) is before


def test_execute_reports_a_raise_from_a_c_target_as_the_targets() -> None:
    # math.isclose runs in C and leaves no frame, so the traceback holds only pyct's frames
    near = functools.partial(math.isclose, rel_tol=0.0)
    ctx = ExecutionContext(fn=near, file=str(FIXTURE))

    result = execute(ctx, {"a": 1, "b": "x"})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED
    assert result.failure.traceback is None


def test_execute_reports_a_raise_before_a_c_target_ran_as_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    near = functools.partial(math.isclose, rel_tol=0.0)
    ctx = ExecutionContext(fn=near, file=str(FIXTURE))
    monkeypatch.setattr(signal, "setitimer", _overflow_on_arming)

    result = execute(ctx, {"a": 1, "b": 1}, time.monotonic() + 1)

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG


def test_execute_reports_a_pyct_raise_below_a_c_target_as_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Site:
        raise RuntimeError("boom")

    # bisect_right runs in C and compares `x < a[mid]`, which lands in pyct's own frames
    target = functools.partial(bisect.bisect_right, [1, 2, 3])
    ctx = ExecutionContext(fn=target, file=str(FIXTURE))
    monkeypatch.setattr(values, "caller_site", broken)

    result = execute(ctx, {"x": 2})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail == "RuntimeError: boom"
    assert result.failure.traceback is not None
