"""The code a seeds ask sends: the target's, then its same-package callees, breadth first."""

import inspect

import pytest

from pyct.run.code_context import code_context
from pyct.run.target import Target, load_target


def headers(code: str) -> list[str]:
    return [line for line in code.splitlines() if line.startswith("# ")]


def test_the_target_comes_first_then_a_callee_in_another_module_of_its_package() -> None:
    code = code_context(load_target("targets.llm.seeds::f"))

    assert headers(code) == ["# targets.llm.seeds.f", "# targets.llm.helpers.sign"]
    assert "def f(x: int):\n    if x == 1234:" in code
    assert "def sign(x: int) -> int:" in code


def test_callees_go_breadth_first_once_each_and_none_from_another_package() -> None:
    code = code_context(load_target("targets.llm.calls::outer"))

    # outer calls sign and middle, middle calls outer again and last; json.dumps and len are
    # not the package's, and last's calls on a local list, through a module's own __getattr__
    # and on a subscript lead to no function pyct reads without running code
    assert headers(code) == [
        "# targets.llm.calls.outer",
        "# targets.llm.helpers.sign",
        "# targets.llm.calls.middle",
        "# targets.llm.calls.last",
    ]


def test_a_method_brings_its_class_s_constructor() -> None:
    code = code_context(load_target("targets.classes.cart::Cart.total"))

    assert headers(code) == [
        "# targets.classes.cart.Cart.total",
        "# targets.classes.cart.Cart.__init__",
    ]
    # a method's code keeps its own indentation out
    assert "def total(self, discount):\n    self.last = discount" in code


def test_the_code_holds_whole_functions_up_to_the_limit() -> None:
    whole = code_context(load_target("targets.llm.calls::outer"))
    sections = whole.split("\n\n# ")

    cut = code_context(load_target("targets.llm.calls::outer"), limit=len(sections[0]) + 5)

    # the target always goes whole; a callee that does not fit is left out, never cut
    assert headers(cut) == ["# targets.llm.calls.outer"]
    assert cut == sections[0]


def test_a_method_s_calls_through_self_and_its_class_lead_to_the_class_s_functions() -> None:
    code = code_context(load_target("targets.llm.calls::Counter.bump"))

    assert headers(code) == [
        "# targets.llm.calls.Counter.bump",
        "# targets.llm.calls.Counter.__init__",
        "# targets.llm.calls.Counter.step",
        "# targets.llm.calls.Counter.twice",
    ]


def test_a_class_called_through_cls_leads_to_its_constructor() -> None:
    code = code_context(load_target("targets.classes.cart::Cart.from_text"))

    assert headers(code) == [
        "# targets.classes.cart.Cart.from_text",
        "# targets.classes.cart.Cart.__init__",
    ]


def test_a_function_python_has_no_source_for_is_left_out() -> None:
    made = eval("lambda x: x")  # noqa: S307
    target = Target("m::made", made, "m.py", inspect.signature(made))

    assert code_context(target) == ""


def helper(x: int) -> int:
    return x + 1


class Notes:
    def told(self, x: int) -> int:
        text = """
this line starts at column 0, so dedenting leaves the method indented
"""
        return helper(x) + len(text)


def here(name: str, fn: object) -> Target:
    return Target(f"{__name__}::{name}", fn, __file__, inspect.signature(fn))  # type: ignore[arg-type]


def test_a_method_holding_a_string_line_at_column_0_still_leads_to_its_callees() -> None:
    code = code_context(here("Notes.told", Notes.told))

    assert headers(code) == [f"# {__name__}.Notes.told", f"# {__name__}.helper"]
    assert "this line starts at column 0" in code


def nowhere(x: int) -> int:
    return x


nowhere.__module__ = None  # type: ignore[assignment]


def calls_nowhere(x: int) -> int:
    return nowhere(x)


def test_a_callee_that_names_no_module_is_left_out() -> None:
    code = code_context(here("calls_nowhere", calls_nowhere))

    assert headers(code) == [f"# {__name__}.calls_nowhere"]


def test_code_python_cannot_parse_alone_leads_to_no_callee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspect, "getsource", lambda _: "    x = (\n")

    code = code_context(here("calls_nowhere", calls_nowhere))

    assert code == f"# {__name__}.calls_nowhere\nx = ("
