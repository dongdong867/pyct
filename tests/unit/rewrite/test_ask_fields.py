"""What a rewrite that reads an object's fields puts in an ask: only what its own code recorded,
never what the child recorded while it built the object; why the reader read no field; and on
which inputs a kept rewrite or a later visit runs it."""

import types
from collections.abc import Mapping

from pyct.binding.annotations import Builds
from pyct.binding.bind import Seed
from pyct.core.foundation.branch import Branch, Expression, Fact, Site
from pyct.execution.execute import ExecutionResult
from pyct.rewrite.ask import Unread, recorded, run_on
from pyct.rewrite.condition import HELD_COL, HELD_LINE, Rewrite, rewrite_code
from tests.unit.rewrite.orders import Order

FILE = "<rewrite m:2:7>"
BUILT = Site("m.py", 9, 11)
OWN = Site(FILE, HELD_LINE, HELD_COL)
READ = Site(FILE, 6, 0)
CODE: Expression = ["getattr", "order", "'code'"]


def field_rewrite(expression: str = 'order.code == "1e-30"') -> Rewrite:
    rewrite = rewrite_code(expression, ("order", "s"), FILE, (), ("order",))
    assert isinstance(rewrite, Rewrite), rewrite
    return rewrite


def test_the_ask_leaves_out_what_the_child_recorded_building_the_object() -> None:
    built = Branch(["startswith", CODE, "' '"], False, BUILT)
    strip = Branch([">", ["len", CODE], 0], True, READ)
    own = Branch(["==", CODE, "'1e-30'"], False, OWN)
    built_fact = Fact(["!=", CODE, "'x'"], True, BUILT, after=0)
    own_fact = Fact(["!=", CODE, "'y'"], True, READ, after=2)
    result = ExecutionResult(frozenset(), (built, strip, own), facts=(built_fact, own_fact))

    items = recorded(result, field_rewrite())

    assert not isinstance(items, str)
    assert items.items == (strip, own_fact.placed_after(1), Branch(own.expression, True, OWN))
    assert items.met is False


def test_a_field_the_reader_read_nothing_of_fails_with_its_reason() -> None:
    reason = "it cannot read order.code: the class reads it with code"

    assert recorded(Unread(reason), field_rewrite()) == reason


def test_a_rewrite_whose_fields_no_input_sets_says_which() -> None:
    rewrite = field_rewrite('order.status == "1e-30" and order.code == order.status')
    built = Branch(["startswith", CODE, "' '"], False, BUILT)

    found = recorded(ExecutionResult(frozenset(), (built,)), rewrite)

    assert found == "it reads no value an input sets: order.status, order.code"


def never(code: types.CodeType, args: Mapping[str, object]) -> ExecutionResult | str:
    raise AssertionError("the rewrite does not run")


def ran(code: types.CodeType, args: Mapping[str, object]) -> ExecutionResult:
    return ExecutionResult(frozenset(), ())


def test_a_field_read_runs_only_where_the_input_holds_the_object() -> None:
    rewrite = field_rewrite()
    form = {"__class__": "m::Order", "code": "0"}

    assert run_on(rewrite, Seed.of({"order": None}), never) is None
    assert run_on(rewrite, Seed.of({"order": {"code": "0"}}), never) is None
    assert run_on(rewrite, Seed.of({"order": [form]}), never) is None
    assert run_on(rewrite, Seed.of({"order": form}), ran) is not None
    hinted = Seed.of({"order": {"code": "0"}}, {"order": Builds(Order)})
    assert run_on(rewrite, hinted, ran) is not None


def test_a_plain_read_runs_only_where_the_input_holds_it_plain() -> None:
    rewrite = rewrite_code("order == None", ("order",), FILE)
    assert isinstance(rewrite, Rewrite)

    assert run_on(rewrite, Seed.of({"order": {"__class__": "m::Order"}}), never) is None
    assert run_on(rewrite, Seed.of({"order": None}), ran) is not None


def test_the_method_s_self_is_an_object_for_a_field_read() -> None:
    rewrite = rewrite_code('self.code == "1e-30"', ("self",), FILE, (), ("self",))
    assert isinstance(rewrite, Rewrite)
    origin = Seed.of({"self": {"code": "0"}})

    assert run_on(rewrite, origin, never) is None
    assert run_on(rewrite, origin, ran, "self") is not None
