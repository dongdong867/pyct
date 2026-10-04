"""A raise under a bound `len`, `ord` or `chr`: the target's, unless core's own frame sits below."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pyct.core import str_lengths
from pyct.core.bound import chr as chr_
from pyct.core.bound import len as len_
from pyct.core.bound import ord as ord_
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import FailureKind

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


class Crate:
    """A container of the target's own whose `__len__` raises."""

    def __len__(self) -> int:
        raise ZeroDivisionError("the crate's own raise")


def failed(target: Callable[..., object], args: dict[str, object]) -> tuple[FailureKind, str]:
    """How one call of the target ended: its failure's kind and detail."""
    result: ExecutionResult = execute(ExecutionContext(fn=target, file=str(FIXTURE)), args)
    assert result.failure is not None
    return result.failure.kind, result.failure.detail


def test_python_s_own_raise_under_a_bound_builtin_is_the_target_s() -> None:
    def sized(n: int) -> object:
        return len_(n)

    def below_zero(n: int) -> object:
        return chr_(n - 10)

    kind, detail = failed(sized, {"n": 5})
    assert (kind, detail.split(":")[0]) == (FailureKind.TARGET_RAISED, "TypeError")
    kind, detail = failed(below_zero, {"n": 5})
    assert (kind, detail.split(":")[0]) == (FailureKind.TARGET_RAISED, "ValueError")


def test_a_raise_in_the_target_s_own_len_under_a_bound_len_is_the_target_s() -> None:
    def target(n: int) -> object:
        return len_(Crate())

    assert failed(target, {"n": 1}) == (
        FailureKind.TARGET_RAISED,
        "ZeroDivisionError: the crate's own raise",
    )


def test_core_s_refusal_of_a_tracked_value_is_the_target_s() -> None:
    def target(c: str) -> object:
        return ord_(c)

    kind, detail = failed(target, {"c": "ab"})
    assert (kind, detail.split(":")[0]) == (FailureKind.TARGET_RAISED, "TypeError")


def test_a_raise_in_core_s_own_code_under_a_bound_len_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("a pyct bug")

    # core's own length builds its answer here, below the routers
    monkeypatch.setattr(str_lengths, "ConcolicInt", broken)

    def target(s: str) -> object:
        return len_(s)

    assert failed(target, {"s": "abc"})[0] is FailureKind.PYCT_BUG
