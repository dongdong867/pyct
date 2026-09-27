"""A line's way, read from the compiled code: the conditions every run passes to reach it."""

import textwrap
import types

import pytest

from pyct.results.way import Flow, Step, StepKind, owners


def code_of(source: str, name: str = "f") -> types.CodeType:
    """The code of the function ``name`` that ``source`` defines at module level."""
    module = compile(textwrap.dedent(source), "m.py", "exec")
    return next(
        constant
        for constant in module.co_consts
        if isinstance(constant, types.CodeType) and constant.co_name == name
    )


def condition(line: int, col: int, side: bool, reaches: int | None) -> Step:
    return Step(kind=StepKind.CONDITION, line=line, col=col, side=side, reaches=reaches)


UNTAKEN = """\
def f(x):
    # a comment line, so the lines match the acceptance target
    if x != x:
        return "never"
    return "always"
"""


def test_a_line_under_an_if_needs_its_true_side() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset())

    assert flow.way(4) == (condition(3, 7, True, 4),)


def test_a_line_after_an_early_return_needs_the_false_side() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset())

    # the AST would put line 5 under no condition; the compiled code sees the return
    assert flow.way(5) == (condition(3, 7, False, 5),)


def test_the_way_lists_the_conditions_in_the_order_the_function_tests_them() -> None:
    source = """\
    def f(x, y):
        if x > 0:
            if y > 0:
                return "deep"
        return "shallow"
    """
    flow = Flow(code_of(source), raising=frozenset())

    assert flow.way(4) == (condition(2, 7, True, 3), condition(3, 11, True, 4))


def test_both_parts_of_an_and_are_on_the_way() -> None:
    source = """\
    def f(x, y):
        if x > 0 and y > 0:
            return 1
        return 0
    """
    flow = Flow(code_of(source), raising=frozenset())

    # the second part's side sits on the same line, so the first part's side reaches no new line
    assert flow.way(3) == (condition(2, 7, True, None), condition(2, 17, True, 3))


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

    assert flow.way(3) == (condition(2, 10, True, 3),)
    assert flow.way(5) == (condition(4, 13, True, 5),)
    # the while loop leaves by its test at the top or at the bottom, so neither is every run's
    # way on; the for loop with no break leaves only when its items run out
    assert flow.way(6) == (condition(4, 13, False, 6),)


def test_a_raising_operation_s_fork_puts_the_lines_after_it_on_its_true_side() -> None:
    source = """\
    def f(x):
        y = 10 // (x - x)
        return y
    """
    code = code_of(source)

    assert Flow(code, raising=frozenset({(2, 8)})).way(3) == (condition(2, 8, True, 3),)
    # with no fork recorded there, the division is no condition at all
    assert Flow(code, raising=frozenset()).way(3) == ()


def test_a_truth_test_s_position_is_never_read_as_a_raising_operation() -> None:
    flow = Flow(code_of(UNTAKEN), raising=frozenset({(3, 7)}))

    assert flow.way(4) == (condition(3, 7, True, 4),)


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
    assert [step.reaches for step in steps] == [4, 5]
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
