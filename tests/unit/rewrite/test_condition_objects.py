"""A rewrite reads a parameter that is an object only as ``name.field``, one level deep: the form
check refuses every other use of the name before anything runs, and each field read is written as
a call of pyct's reader, which the child runs on the object the input builds."""

import time

import pytest

from pyct.binding.stored import read_field
from pyct.intercept.model_code import Refused
from pyct.rewrite.condition import FUNCTION, HELD_COL, HELD_LINE, READER, Rewrite, rewrite_code
from pyct.run import model_runs
from pyct.run.model_runs import ModelCall, ModelRun, run_model
from tests.unit.rewrite.orders import Order

FILE = "<rewrite m:2:7>"
PARAMETERS = ("order", "s", "orders")
# order is an object and orders holds one
FIELDS = ("order",)
OBJECTS = ("orders",)
WHOLE = "a rewrite may read order only as order.<field>"


@pytest.fixture(autouse=True)
def _one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)


def checked(expression: str, parameters: tuple[str, ...] = PARAMETERS) -> Rewrite | Refused:
    return rewrite_code(expression, parameters, FILE, OBJECTS, FIELDS)


def refusal(expression: str) -> str:
    code = checked(expression)
    assert isinstance(code, Refused), expression
    return code.reason


def test_a_field_read_passes_and_names_the_field() -> None:
    rewrite = checked('order.code == "1e-30" and s == "0"')

    assert isinstance(rewrite, Rewrite), rewrite
    assert rewrite.reads == ("order", "s")
    assert rewrite.fields == ("order.code",)


def test_a_method_of_a_field_s_value_passes() -> None:
    rewrite = checked('order.code.strip().upper() == "X" and len(order.tags[0]) > 1')

    assert isinstance(rewrite, Rewrite), rewrite
    assert rewrite.fields == ("order.code", "order.tags")


def test_a_method_of_the_object_is_refused() -> None:
    assert refusal("order.cancel() == 1") == "a rewrite may not call a method of order"
    assert refusal("order._save() == 1") == "a rewrite may not call a method of order"


@pytest.mark.parametrize(
    "expression",
    [
        "order == 1",
        "1 == order",
        "order != 1",
        "1 < order",
        "len(order) == 1",
        "bool(order)",
        "not order",
        'str(order) == "x"',
        '"%s" % order == "x"',
        "order in [1]",
        "1 in order",
        "[1][order] == 1",
        "order[0] == 1",
        'order["code"] == "1e-30"',
        '"".join(order) == ""',
        "float(order) == 1.0",
        "int(order) == 1",
        "order + 1 == 1",
        "s.count(order) == 1",
        "min(order, 1) == 1",
    ],
)
def test_the_object_used_whole_is_refused(expression: str) -> None:
    assert refusal(expression) == WHOLE


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ('order.__dict__["code"] == "1e-30"', "a rewrite may not read the attribute __dict__"),
        ("order.__class__ == 1", "a rewrite may not read the attribute __class__"),
        ('order.code.__class__ == "x"', "a rewrite may not read the attribute __class__"),
        ('order.code.real == "x"', "a rewrite may not read the attribute real"),
        ("s.real > 0", "a rewrite may not read the attribute real"),
        ("order.code.__len__() == 1", "a rewrite may not call __len__"),
        ('orders[0].code == "1e-30"', "a rewrite may not read orders, which holds an object"),
        (f'{READER}(order, "order", "code") == 1', f"a rewrite may not call {READER}"),
    ],
)
def test_any_other_attribute_is_refused(expression: str, reason: str) -> None:
    assert refusal(expression) == reason


def test_a_field_of_a_field_is_refused() -> None:
    code = rewrite_code('account.owner.code == "1e-30"', ("account",), FILE, (), ("account",))

    assert isinstance(code, Refused)
    assert code.reason == "a rewrite may not read the attribute code"


def test_a_field_read_runs_through_the_reader_on_the_object() -> None:
    rewrite = checked('order.code == "1e-30"')
    assert isinstance(rewrite, Rewrite), rewrite
    call = ModelCall(rewrite.code, FUNCTION, {"order": Order("0")}, {READER: read_field})

    done = run_model(call, time.monotonic() + 5)

    assert isinstance(done, ModelRun)
    assert done.result.failure is None, done.result.failure
    [own] = [
        fork
        for fork in done.result.branches
        if (fork.site.line, fork.site.col) == (HELD_LINE, HELD_COL)
    ]
    assert own.expression == ["==", ["getattr", "order", "'code'"], "'1e-30'"]
    assert own.taken is False
