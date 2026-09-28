"""A raise under a substituted `in`: the target's, unless a frame of core's own sits below."""

import functools
from pathlib import Path

import pytest

from pyct.core import strs
from pyct.core.substitutes import Searched, in_
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


class Equal:
    """An element the target put in a set: it hashes as the int 1, and its `__eq__` raises."""

    def __hash__(self) -> int:
        return 1

    def __eq__(self, other: object) -> bool:
        raise ZeroDivisionError("the element's own raise")


class Unordered:
    """An operand of the target's own whose `<` raises."""

    def __lt__(self, other: object) -> bool:
        raise ZeroDivisionError("the operand's own raise")


def blamed(target: object, seed: dict[str, object]) -> tuple[FailureKind, str]:
    """How the one input ended, and its detail."""
    result = execute(ExecutionContext(fn=target, file=str(FIXTURE)), seed)  # pyrefly: ignore
    assert result.failure is not None
    return result.failure.kind, result.failure.detail


def test_a_raise_in_python_s_own_lookup_of_a_searched_set_is_the_target_s() -> None:
    def target(n: int) -> object:
        return in_(n, {Equal()})

    assert blamed(target, {"n": 1}) == (
        FailureKind.TARGET_RAISED,
        "ZeroDivisionError: the element's own raise",
    )


def test_a_raise_under_a_chain_s_searched_link_is_the_target_s() -> None:
    def target(n: int) -> object:
        return n in Searched(Box())

    assert blamed(target, {"n": 1}) == (
        FailureKind.TARGET_RAISED,
        "ZeroDivisionError: the box's own raise",
    )


def test_a_raise_in_a_compare_a_link_hands_on_is_the_target_s() -> None:
    def target(n: int) -> object:
        return Searched(Unordered()) < n

    assert blamed(target, {"n": 1}) == (
        FailureKind.TARGET_RAISED,
        "ZeroDivisionError: the operand's own raise",
    )


class Truthless:
    """An answer of the target's whose `__bool__` hands back an int, which Python refuses."""

    def __bool__(self) -> int:  # pyrefly: ignore[bad-return]
        return 1


class Answering:
    """An element of the target's whose `==` answers with a `Truthless`."""

    def __eq__(self, other: object) -> object:  # pyrefly: ignore[bad-override]
        return Truthless()

    __hash__ = object.__hash__


def test_a_raise_in_python_s_own_truth_test_of_a_walked_element_is_the_target_s() -> None:
    def target(n: int) -> object:
        return in_(n, (Answering(),))

    kind, detail = blamed(target, {"n": 1})
    assert kind is FailureKind.TARGET_RAISED
    with pytest.raises(TypeError) as raised:
        bool(Answering() == 1)
    assert detail == f"TypeError: {raised.value}"
