"""A call on model-written code builds the objects its arguments name as an input of the target
does, with the target's home module, hints and the build of a method's ``self``, passed first;
and a raise of one of the call's own ending errors ends it with that error's text, not as a
raise."""

import time
import types

import pytest

from pyct.binding.annotations import Builds
from pyct.binding.builds import SelfBuild
from pyct.binding.hints import inside_of
from pyct.intercept.model_code import compile_model_code
from pyct.run import model_runs
from pyct.run.model_runs import Building, ModelCall, ModelRun, run_model
from tests.unit.rewrite.orders import Order

FILE = "<model m:2:7>"
HOME = "tests.unit.rewrite.orders"


@pytest.fixture(autouse=True)
def _one_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)


class EndedError(Exception):
    """An error of the call's own that ends it with its text."""


def ended(reason: str) -> None:
    raise EndedError(reason)


def code_of(text: str) -> types.CodeType:
    code = compile_model_code(text, FILE, lambda tree: tree)
    assert isinstance(code, types.CodeType)
    return code


def ran(call: ModelCall) -> ModelRun:
    done = run_model(call, time.monotonic() + 5)
    assert isinstance(done, ModelRun)
    return done


def test_an_object_named_by_a_bare_class_name_is_built_in_the_home_module() -> None:
    call = ModelCall(
        code_of("def f(order):\n    return type(order).__name__ + order.code\n"),
        "f",
        {"order": {"__class__": "Order", "code": "0"}},
        building=Building(home=HOME),
    )

    done = ran(call)

    assert done.result.failure is None, done.result.failure
    assert done.answer == '"Order0"'


def test_an_object_a_hint_builds_is_built() -> None:
    call = ModelCall(
        code_of("def f(order):\n    return type(order).__name__\n"),
        "f",
        {"order": {"code": "0"}},
        building=Building(checks={"order": Builds(Order), "other": Builds(Order)}),
    )

    assert ran(call).answer == '"Order"'


def test_the_instance_a_method_runs_on_is_built_and_passed_first() -> None:
    call = ModelCall(
        code_of("def f(self, n):\n    return [type(self).__name__, self.code, n]\n"),
        "f",
        {"n": 1, "self": {"code": "0"}},
        building=Building(
            checks={"self": inside_of(Order).keys}, self_build=SelfBuild(Order, "self")
        ),
    )

    done = ran(call)

    assert done.result.failure is None, done.result.failure
    assert done.answer == '["Order", "0", 1]'


def test_a_call_without_the_method_s_instance_builds_none() -> None:
    call = ModelCall(
        code_of("def f(n):\n    return n\n"),
        "f",
        {"n": 1},
        building=Building(self_build=SelfBuild(Order, "self")),
    )

    assert ran(call).answer == "1"


def test_an_ending_error_ends_the_call_with_its_text() -> None:
    call = ModelCall(
        code_of("def f(n):\n    if n > 0:\n        stop('it cannot read it')\n    return n\n"),
        "f",
        {"n": 1},
        {"stop": ended},
        ends=(EndedError,),
    )

    done = ran(call)

    assert done.ended == "it cannot read it"
    assert done.answer is None
    assert done.result.failure is None
    assert [fork.taken for fork in done.result.branches] == [True]


def test_another_raise_of_the_names_is_pyct_s_own() -> None:
    call = ModelCall(code_of("def f(n):\n    stop('no')\n"), "f", {"n": 1}, {"stop": ended})

    done = ran(call)

    assert done.ended is None
    assert done.result.failure is not None
