"""CodeWays reads a code object's branches, and the way each BRANCH event went, by line."""

import dis
import types

from pyct.execution.branch_ways import CodeWays

LOOPS = """\
def f(s):
    t = 0
    while s != "":
        if "z" in s:
            t += 1
        s = s[:-1]
    for c in s:
        if c == "x":
            t += 1
    if t > 5:
        return 1
    return 0
"""

CONDITIONS = """\
def f(a, b, s):
    if a and b:
        x = 1
    else:
        x = 2
    if (a or
            b):
        x = 3
    y = 1 if a else 2
    try:
        z = int(s)
    except ValueError:
        z = 0
    if a: return 1
    return x, y, z
"""


def function_code(source: str) -> types.CodeType:
    """The code of ``f`` in the source."""
    module = compile(source, "<ways>", "exec")
    return next(c for c in module.co_consts if isinstance(c, types.CodeType) and c.co_name == "f")


def test_a_loop_s_test_leads_into_its_body_and_past_it() -> None:
    ways = CodeWays(function_code(LOOPS))

    assert ways.branches == {
        3: {4, 7},
        4: {5, 6},
        7: {8, 10},
        # the way an `if` at a loop body's end does not take goes back to the loop's test
        8: {7, 9},
        10: {11, 12},
    }


def test_a_way_is_counted_by_the_line_it_leads_to() -> None:
    ways = CodeWays(function_code(CONDITIONS))

    # line 2's two tests lead to lines 3 and 5, and each test of lines 6 and 7 leads on
    assert ways.branches[2] == {3, 5}
    assert ways.branches[6] == {7, 8}
    assert ways.branches[7] == {8, 9}


def test_ways_that_stay_on_their_line_or_raise_make_no_branch() -> None:
    ways = CodeWays(function_code(CONDITIONS))

    # line 9 tests and stays on its line; line 12's other way raises again; line 14's returns
    # on its own line
    assert 9 not in ways.branches
    assert 12 not in ways.branches
    assert 14 not in ways.branches


def test_lines_are_every_line_the_line_table_names() -> None:
    code = function_code(LOOPS)

    assert CodeWays(code).lines == {line for _, _, line in code.co_lines() if line}


def test_way_turns_an_event_into_the_branch_line_and_the_line_it_led_to() -> None:
    code = function_code(CONDITIONS)
    ways = CodeWays(code)
    test = next(i for i in dis.get_instructions(code) if i.opname.startswith("POP_JUMP_IF"))

    assert ways.way(test.offset, test.argval) == (2, 5)
    # read again, it is the same way
    assert ways.way(test.offset, test.argval) == (2, 5)


def test_way_is_none_off_a_branch_line_or_on_the_test_s_own_line() -> None:
    code = function_code(CONDITIONS)
    ways = CodeWays(code)
    instructions = list(dis.get_instructions(code))
    tests = [i for i in instructions if i.opname.startswith("POP_JUMP_IF")]
    on_line_9 = next(i for i in tests if i.positions is not None and i.positions.lineno == 9)
    first = tests[0]
    after_first = instructions[instructions.index(first) + 1]

    assert ways.way(on_line_9.offset, on_line_9.argval) is None
    # `a and b`: the first test's way when `a` holds goes on to `b`, on its own line
    assert ways.way(first.offset, after_first.offset) is None


def test_way_is_none_to_a_target_no_instruction_starts_at() -> None:
    code = function_code(CONDITIONS)
    test = next(i for i in dis.get_instructions(code) if i.opname.startswith("POP_JUMP_IF"))

    assert CodeWays(code).way(test.offset, 1_000_000) is None
