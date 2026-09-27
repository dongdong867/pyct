"""A raise under a substituted `in`: the target's, unless a frame of core's own sits below."""

import functools
from pathlib import Path

import pytest

from pyct.core import strs
from pyct.core.substitutes import in_
from pyct.execution.execute import ExecutionContext, execute
from pyct.results.failure import FailureKind

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


class Box:
    """A container of the target's own whose `__contains__` raises."""

    def __contains__(self, item: object) -> bool:
        raise ZeroDivisionError("the box's own raise")


def test_a_membership_type_error_under_the_substituted_in_is_the_target_s() -> None:
    def target(n: int) -> object:
        return in_(n, "abc")

    result = execute(ExecutionContext(fn=target, file=str(FIXTURE)), {"n": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED
    assert result.failure.detail.startswith("TypeError:")


def test_a_raise_in_the_target_s_own_contains_under_the_substituted_in_is_the_target_s() -> None:
    def target(n: int) -> object:
        return in_(n, Box())

    result = execute(ExecutionContext(fn=target, file=str(FIXTURE)), {"n": 1})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED
    assert result.failure.detail == "ZeroDivisionError: the box's own raise"


def test_a_raise_in_core_s_own_code_under_the_substituted_in_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(args: tuple[object, ...]) -> object:
        raise RuntimeError("a pyct bug")

    monkeypatch.setattr(strs, "_needle", broken)

    def target(s: str) -> object:
        return in_("a", s)

    result = execute(ExecutionContext(fn=target, file=str(FIXTURE)), {"s": "abc"})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG


def test_a_codeless_target_that_is_the_substituted_in_reads_through_it() -> None:
    # a callable with no code of its own runs the frame right under the caller's: here that
    # frame is the router's, which blame reads through
    result = execute(
        ExecutionContext(fn=functools.partial(in_, container="abc"), file=str(FIXTURE)),
        {"item": 1},
    )

    assert result.failure is not None
    assert result.failure.kind is FailureKind.TARGET_RAISED
