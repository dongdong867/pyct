"""A line's way, read from the compiled code: the conditions every run passes to reach it."""

import textwrap
import types

import pytest

from pyct.results.blocks import owners
from pyct.results.way import Flow, Step, StepKind


def code_of(source: str, name: str = "f") -> types.CodeType:
    """The code of the function ``name`` that ``source`` defines at module level."""
    module = compile(textwrap.dedent(source), "m.py", "exec")
    return next(
        constant
        for constant in module.co_consts
        if isinstance(constant, types.CodeType) and constant.co_name == name
    )


def condition(line: int, col: int, side: bool, *, raising: bool = False) -> Step:
    return Step(kind=StepKind.CONDITION, line=line, col=col, side=side, raising=raising)


UNTAKEN = """\
def f(x):
    # a comment line, so the lines match the acceptance target
    if x != x:
        return "never"
    return "always"
"""


def test_a_line_under_an_if_needs_its_true_side() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset())

    assert flow.way(4) == (condition(3, 7, True),)


def test_a_line_after_an_early_return_needs_the_false_side() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset())

    # the AST would put line 5 under no condition; the compiled code sees the return
    assert flow.way(5) == (condition(3, 7, False),)


def test_the_way_lists_the_conditions_in_the_order_the_function_tests_them() -> None:
    source = """\
    def f(x, y):
        if x > 0:
            if y > 0:
                return "deep"
        return "shallow"
    """
    flow = Flow(code_of(source), raising=frozenset())

    assert flow.way(4) == (condition(2, 7, True), condition(3, 11, True))


def test_both_parts_of_an_and_are_on_the_way() -> None:
    source = """\
    def f(x, y):
        if x > 0 and y > 0:
            return 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())

    assert flow.way(3) == (condition(2, 7, True), condition(2, 17, True))


def test_a_loop_body_needs_the_loop_to_go_on_and_a_for_loop_s_end_needs_it_to_run_out() -> None:
    source = """\
    def f(x):
        while x > 0:
            x -= 1
        for c in "ab":
            x += 1
        return x
    """
    flow = Flow(code_of(source), raising=frozenset())

    assert flow.way(3) == (condition(2, 10, True),)
    assert flow.way(5) == (condition(4, 13, True),)
    # the while loop leaves by its test at the top or at the bottom, so neither is every run's
    # way on; the for loop with no break leaves only when its items run out
    assert flow.way(6) == (condition(4, 13, False),)


def test_a_raising_operation_s_fork_puts_the_lines_after_it_on_its_true_side() -> None:
    source = """\
    def f(x):
        y = 10 // (x - x)
        return y
    """
    code = code_of(source)

    assert Flow(code, raising=frozenset({(2, 8)})).way(3) == (condition(2, 8, True, raising=True),)
    # with no fork recorded there, the division is no condition at all
    assert Flow(code, raising=frozenset()).way(3) == ()


def test_an_operation_s_fork_at_a_test_s_column_goes_before_the_test() -> None:
    source = """\
    def f(x):
        if 10 // x > 100:
            return 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset({(2, 7)}))

    # the division's fork and the compare's test share 2:7; the division runs first
    assert flow.way(3) == (condition(2, 7, True, raising=True), condition(2, 7, True))
    assert flow.way(4) == (condition(2, 7, True, raising=True), condition(2, 7, False))


HANDLER = """\
def f(x):
    try:
        n = int("5")
    except ValueError:
        return "bad"
    return n + x
"""


def test_a_line_in_an_except_block_is_reached_only_through_the_handler() -> None:
    flow = Flow(code_of(HANDLER), raising=frozenset())

    steps = flow.way(5)

    # into the handler, then past its match
    assert [step.kind for step in steps] == [StepKind.HANDLER, StepKind.HANDLER]
    assert [step.line for step in steps] == [4, 4]
    assert flow.only_in_handlers(5)
    assert flow.only_in_handlers(4)


def test_a_line_after_the_try_is_not_in_a_handler() -> None:
    flow = Flow(code_of(HANDLER), raising=frozenset())

    assert flow.way(6) == ()
    assert not flow.only_in_handlers(6)


def test_a_delegating_generator_s_send_loop_is_no_condition() -> None:
    source = """\
    def f(xs):
        yield from xs
        return 1
    """
    flow = Flow(code_of(source), raising=frozenset())

    # `yield from` loops on its sends until the inner one is done; no value is tested there
    assert flow.way(3) == ()


def test_a_line_the_code_does_not_hold_has_no_way() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset())

    assert flow.way(99) == ()
    assert not flow.only_in_handlers(99)


MODULE = """\
import os

LIMIT = 10


def f(x):
    def inner(y):
        return y
    return inner(x)


class Cart:
    size = 2

    def total(self):
        return self.size


def g(x):
    class Local:
        z = x
    return Local
"""


@pytest.fixture
def module_owners() -> dict[int, str | None]:
    """Each line's owner by its qualified name, None when import runs it."""
    module = compile(MODULE, "m.py", "exec")
    return {
        line: None if code is None else code.co_qualname for line, code in owners(module).items()
    }


def test_import_owns_module_level_lines_def_lines_and_class_bodies(
    module_owners: dict[int, str | None],
) -> None:
    for line in (1, 3, 6, 12, 13, 15, 19):
        assert module_owners[line] is None, line


def test_the_outermost_function_that_runs_a_line_owns_it(
    module_owners: dict[int, str | None],
) -> None:
    # the inner def line runs when f runs; its body only when inner does
    assert module_owners[7] == "f"
    assert module_owners[8] == "f.<locals>.inner"
    assert module_owners[9] == "f"
    assert module_owners[16] == "Cart.total"


def test_a_class_body_inside_a_function_runs_when_its_function_does(
    module_owners: dict[int, str | None],
) -> None:
    assert module_owners[20] == "g"
    assert module_owners[21] == "g.<locals>.Local"


GUARDED = """\
def f(x, m, xs):
    if x > 0:
        with m:
            a = 1
        b = [v for v in xs]
        try:
            c = 1
        finally:
            d = 2
        try:
            e = int(x)
        except ValueError:
            g = 3
        return a
    return 0
"""


@pytest.mark.parametrize("line", [3, 4, 5, 6, 7, 9, 10, 11, 14])
def test_a_guard_around_code_python_copies_into_a_handler_is_on_every_copy_s_way(
    line: int,
) -> None:
    flow = Flow(code_of(GUARDED), raising=frozenset())

    # the with line, the comprehension and the finally body sit in cleanup code as well
    assert flow.way(line)[:1] == (condition(2, 7, True),), line


def test_an_except_block_under_a_guard_needs_the_guard_and_then_the_raise() -> None:
    flow = Flow(code_of(GUARDED), raising=frozenset())

    steps = flow.way(13)

    # the guard, the comprehension's loop running out, then the raise and the clause's match
    assert steps[:2] == (condition(2, 7, True), condition(5, 24, False))
    assert [step.kind for step in steps[2:]] == [StepKind.HANDLER, StepKind.HANDLER]
    assert flow.only_in_handlers(13)


def test_the_lines_after_an_await_under_a_guard_need_the_guard() -> None:
    source = """\
    async def f(x, g):
        if x > 0:
            await g()
            a = 1
            return a
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())

    for line in (3, 4, 5):
        assert flow.way(line) == (condition(2, 7, True),), line


def test_the_lines_after_a_yield_from_under_a_guard_need_the_guard() -> None:
    source = """\
    def f(x):
        if x > 0:
            yield from range(3)
            b = 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())

    for line in (3, 4):
        assert flow.way(line) == (condition(2, 7, True),), line


def test_a_line_either_side_of_an_or_reaches_has_both_sides_reaching_it_in_test_order() -> None:
    source = """\
    def f(x):
        if x > 0 or x < -5:
            return 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())

    assert flow.way(3) == ()
    reaching = [place.step for place in flow.reaching(3)]
    # the first test's true side, then its false side on to the second, then the second's
    assert reaching == [condition(2, 7, True), condition(2, 7, False), condition(2, 16, True)]


def test_a_ternary_s_sides_show_nothing_a_run_could_cover() -> None:
    source = """\
    def f(x):
        y = 1 if x > 0 else 2
        if y > 5:
            return 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())
    ternary = [place for place in flow.reaching(4) if place.step.line == 2]
    test = [place for place in flow.reaching(4) if place.step.line == 3]

    assert ternary
    assert not any(flow.knowable(place) for place in ternary)
    assert [flow.knowable(place) for place in test] == [True]
