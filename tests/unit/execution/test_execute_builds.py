"""How execute builds each object a seed names inside the call, and whose a raise there is."""

import datetime
import time
from pathlib import Path

import pytest

from pyct.core.foundation import values
from pyct.core.foundation.branch import Site
from pyct.execution.blame import one_line
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure, FailureKind
from tests.unit.deadline_fires import DEADLINE_FIRES

FILE = str(Path(__file__).resolve())
HOME = __name__


class Customer:
    def __init__(self, name: str, age: int) -> None:
        if age < 0:
            raise ValueError("negative age")
        if age == 99:
            raise SystemExit(4)
        self.name = name
        self.age = age


class Order:
    def __init__(self, customer: Customer, total: int) -> None:
        if total < 0:
            raise ValueError("negative total")
        self.customer = customer
        self.total = total


class Stalls:
    def __init__(self, seconds: float) -> None:
        time.sleep(seconds)


def ship(o: Order) -> str:
    if o.customer.age > 60:
        return "care"
    return "standard"


def stalled(s: Stalls) -> None:
    return None


def dated(d: datetime.date) -> int:
    return d.month


def executed(fn: object, args: dict[str, object], until: float | None = None) -> ExecutionResult:
    ctx = ExecutionContext(fn=fn, file=FILE, home=HOME)  # pyrefly: ignore[bad-argument-type]
    return execute(ctx, args, until)


def order(age: int, total: int = 5) -> dict[str, object]:
    customer = {"__class__": "Customer", "name": "ann", "age": age}
    return {"o": {"__class__": "Order", "customer": customer, "total": total}}


def test_each_object_is_built_innermost_first_and_its_forks_are_followed() -> None:
    result = executed(ship, order(30))

    age = ["[]", ["[]", "o", "'customer'"], "'age'"]
    assert result.failure is None
    assert [branch.expression for branch in result.branches] == [
        ["<", age, 0],
        ["==", age, 99],
        ["<", ["[]", "o", "'total'"], 0],
        [">", age, 60],
    ]


def test_an_inner_constructor_s_raise_names_its_place() -> None:
    result = executed(ship, order(-1))

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="building o['customer']: ValueError: negative age"
    )


def test_an_outer_constructor_s_raise_names_its_place() -> None:
    result = executed(ship, order(30, total=-1))

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail="building o: ValueError: negative total"
    )


def test_a_system_exit_in_an_inner_constructor_keeps_its_kind() -> None:
    result = executed(ship, order(99))

    assert result.failure == Failure(
        kind=FailureKind.SYSTEM_EXIT, detail=f"building o['customer']: {one_line(SystemExit(4))}"
    )


def test_a_raise_in_a_class_written_in_c_is_the_target_s() -> None:
    with pytest.raises(ValueError) as plain:
        datetime.date(2024, 13, 1)

    form = {"__class__": "datetime::date", "year": 2024, "month": 13, "day": 1}
    result = executed(dated, {"d": form})

    detail = f"building d: {one_line(plain.value)}"
    assert result.failure == Failure(kind=FailureKind.TARGET_RAISED, detail=detail)


def test_a_raise_from_pyct_under_a_constructor_is_a_pyct_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Site:
        raise RuntimeError("boom")

    # the constructor's compare reaches this through a frame of pyct's own
    monkeypatch.setattr(values, "caller_site", broken)

    result = executed(ship, order(30))

    assert result.failure is not None
    assert result.failure.kind is FailureKind.PYCT_BUG
    assert result.failure.detail == "RuntimeError: boom"


def test_an_object_that_cannot_be_built_ends_the_input_before_anything_runs() -> None:
    result = executed(ship, {"o": {"__class__": "Nowhere", "total": 1}})

    assert result.failure == Failure(
        kind=FailureKind.TARGET_RAISED, detail=f"building o: {HOME} has no class Nowhere"
    )
    assert result.branches == ()
    assert result.lines == frozenset()


@DEADLINE_FIRES
def test_the_deadline_in_a_constructor_is_a_timeout() -> None:
    started = time.monotonic()

    result = executed(stalled, {"s": {"__class__": "Stalls", "seconds": 3.0}}, started + 0.5)

    assert result.failure == Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")
    assert time.monotonic() - started < 2
