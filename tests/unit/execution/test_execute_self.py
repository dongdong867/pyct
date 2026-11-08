"""How execute builds the instance a method runs on, inside the call, and whose a raise there is."""

import inspect
import time
from pathlib import Path

import pytest

from pyct.binding.annotations import Fields
from pyct.binding.call import positional_only
from pyct.core.foundation import values
from pyct.core.foundation.branch import Site
from pyct.execution.blame import one_line
from pyct.execution.execute import ExecutionContext, ExecutionResult, SelfBuild, execute
from pyct.results.failure import Failure, FailureKind
from tests.unit.deadline_fires import DEADLINE_FIRES

FILE = str(Path(__file__).resolve())
OWNER_IS_ADMIN = ["==", ["[]", "self", "'owner'"], "'admin'"]


class Cart:
    def __init__(self, owner: str) -> None:
        if owner == "":
            raise ValueError("no owner")
        if owner == "quit":
            raise SystemExit(3)
        self.owner = owner

    def total(self, discount: int) -> int:
        if self.owner == "admin":
            return 0
        if discount < 0:
            raise ValueError("below zero")
        return discount


class Ratio(float):
    """A class whose constructor runs in C."""

    def double(self) -> float:
        return self * 2


class Pinned:
    """A constructor and a method whose parameters go by position only."""

    def __init__(self, owner: str, /) -> None:
        self.owner = owner

    def total(self, discount: int, /) -> int:
        if self.owner == "admin":
            return 0
        return discount


# each time a ``Slow``'s ``__del__`` started
DEL_STARTS: list[float] = []


class Slow:
    """An instance whose ``__del__`` outlasts any short deadline."""

    def __init__(self, x: int) -> None:
        self.x = x

    def __del__(self) -> None:
        DEL_STARTS.append(time.monotonic())
        time.sleep(3)

    def m(self) -> int:
        return self.x


def built(
    cls: type, method: object, args: dict[str, object], until: float | None = None
) -> ExecutionResult:
    """One call of ``method`` on an instance of ``cls`` built from ``args['self']``."""
    signature = inspect.signature(method)  # pyrefly: ignore[bad-argument-type]
    constructor = positional_only(inspect.signature(cls))
    ctx = ExecutionContext(
        fn=method,  # pyrefly: ignore[bad-argument-type]
        file=FILE,
        positional=positional_only(signature),
        checks={"self": Fields({})},
        self_build=SelfBuild(cls, "self", constructor),
    )
    return execute(ctx, args, until)


def test_the_method_runs_on_an_instance_built_from_the_seed() -> None:
    result = built(Cart, Cart.total, {"self": {"owner": "ann"}, "discount": 5})

    # the constructor's forks come first, followed as the method's are
    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [
        ["==", ["[]", "self", "'owner'"], "''"],
        ["==", ["[]", "self", "'owner'"], "'quit'"],
        OWNER_IS_ADMIN,
        ["<", "discount", 0],
    ]


def test_a_raise_in_the_constructor_is_the_target_s_and_says_it_came_while_building() -> None:
    result = built(Cart, Cart.total, {"self": {"owner": ""}, "discount": 5})

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="building self: ValueError: no owner"
    )
    assert [branch.expression for branch in result.branches] == [
        ["==", ["[]", "self", "'owner'"], "''"]
    ]


def test_a_raise_in_a_constructor_written_in_c_is_the_target_s() -> None:
    with pytest.raises(ValueError) as plain:
        # float's own parameter goes by position only, as the construction passes it
        Ratio("a")

    result = built(Ratio, Ratio.double, {"self": {"x": "a"}})

    expected = f"building self: {one_line(plain.value)}"
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=expected)


def test_a_system_exit_in_the_constructor_keeps_its_kind() -> None:
    result = built(Cart, Cart.total, {"self": {"owner": "quit"}, "discount": 5})

    assert result.failure == Failure(
        kind=FailureKind.SYSTEM_EXIT, detail=f"building self: {one_line(SystemExit(3))}"
    )


def test_a_raise_from_pyct_under_the_constructor_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Site:
        raise RuntimeError("boom")

    # the constructor's compare reaches this through a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", broken)

    result = built(Cart, Cart.total, {"self": {"owner": "ann"}, "discount": 5})

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail == "RuntimeError: boom"


def test_a_raise_in_the_method_after_the_construction_says_nothing_of_building() -> None:
    result = built(Cart, Cart.total, {"self": {"owner": "ann"}, "discount": -1})

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="ValueError: below zero"
    )


def test_positional_only_parameters_go_by_position_on_both_calls() -> None:
    result = built(Pinned, Pinned.total, {"self": {"owner": "admin"}, "discount": 5})

    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [OWNER_IS_ADMIN]


def test_a_value_that_is_not_a_dict_is_passed_as_self_as_given() -> None:
    result = built(Cart, Cart.total, {"self": Cart("ann"), "discount": 5})

    # the instance's owner is followed by its attribute, as the walk names it
    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [
        ["==", ["getattr", "self", "'owner'"], "'admin'"],
        ["<", "discount", 0],
    ]


@DEADLINE_FIRES
# the alarm lands in `__del__`, where Python reports a raise as unraisable and goes on
@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_the_instance_goes_inside_the_deadline_so_its_del_is_held_to_it() -> None:
    # plain Python drops the instance as the method returns, inside the call
    DEL_STARTS.clear()
    started = time.monotonic()

    built(Slow, Slow.m, {"self": {"x": 1}}, started + 0.5)

    assert len(DEL_STARTS) == 1
    assert time.monotonic() - started < 2
