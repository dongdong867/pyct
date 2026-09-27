"""The lines-up check: what a line tracer and a branch read off compiled code.

Two codes line up when each pair of code objects has the same lines, the same steps from one
line to the next, and the same conditional jumps, each copy counted, at the same position with
the same target line and the same kind. A line start is where ``sys.monitoring`` fires a line
event, so these are the lines a run covers and the order it covers them in. A truth test is
read on the outcome it jumps on, so the two changes of kind allowed keep it: a fused None
test, which a substituted `is None` link makes a truth test, and a truth test after a
`not in` or an `is not`, or pyct's call for one, which reads as the other truth test after
the operator without its `not` (see `jump_kind`). No other instruction is compared:
substitution changes them.
"""

import ast
import dis
import types
from collections.abc import Iterator

from pyct.intercept.substitute import BOUND, substitute

# a place in the source, as `dis` gives an instruction's: line, last line, column, last column
type Span = tuple[int | None, int | None, int | None, int | None]
type Layout = tuple[
    str, frozenset[int], frozenset[tuple[int | None, int]], list[tuple[object, int | None, str]]
]


def code_objects(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from code_objects(constant)


def line_starts(code: types.CodeType) -> list[tuple[int, bool]]:
    """Each instruction after RESUME that starts a line, or that a jump lands on, with its line."""
    starts: list[tuple[int, bool]] = []
    previous: int | None = None
    resumed = False
    for step in dis.get_instructions(code):
        line = step.positions.lineno if step.positions else None
        if resumed and line is not None and (line != previous or step.is_jump_target):
            starts.append((line, step.is_jump_target))
        resumed = resumed or step.opname == "RESUME"
        previous = line
    return starts


# how control leaves an instruction without falling through to the next one
_NO_FALLTHROUGH = frozenset(
    {
        "RETURN_VALUE",
        "RETURN_CONST",
        "RAISE_VARARGS",
        "RERAISE",
        "JUMP_FORWARD",
        "JUMP_BACKWARD",
        "JUMP_BACKWARD_NO_INTERRUPT",
    }
)
_JUMPS = frozenset(dis.hasjrel) | frozenset(dis.hasjabs)


def _successors(steps: list[dis.Instruction]) -> list[list[int]]:
    """The indexes control can go to from each instruction: the next one, and a jump's target."""
    at = {step.offset: index for index, step in enumerate(steps)}
    found: list[list[int]] = []
    for index, step in enumerate(steps):
        after = [] if step.opname in _NO_FALLTHROUGH else [index + 1]
        if step.opcode in _JUMPS and isinstance(step.argval, int) and step.argval in at:
            after.append(at[step.argval])
        found.append([each for each in after if each < len(steps)])
    return found


def _line(step: dis.Instruction) -> int | None:
    """An instruction's line, or None for RESUME and an instruction with no line of its own."""
    if step.opname == "RESUME" or step.positions is None:
        return None
    return step.positions.lineno


def line_order(code: types.CodeType) -> frozenset[tuple[int | None, int]]:
    """Which line can run right after which: each step from one line to another along the code.

    A line start is where ``sys.monitoring`` fires a line event, so these
    steps are the orders a run covers lines in, on every path. CPython copies
    a short block that ends a function, such as its last ``return``, into
    each branch that reaches it, and a longer one it jumps to instead; both
    take the same steps, so two codes that differ only there line up. The
    first line is a step from None, from RESUME, and an instruction with no
    line of its own passes control on without a step.
    """
    steps = [step for step in dis.get_instructions(code) if step.opname != "CACHE"]
    successors = _successors(steps)
    order: set[tuple[int | None, int]] = set()
    for index, step in enumerate(steps):
        start = _line(step)
        if start is None and step.opname != "RESUME":
            continue
        pending, seen = list(successors[index]), set()
        while pending:
            after = pending.pop()
            if after not in seen:
                seen.add(after)
                reached = _line(steps[after])
                if reached is None:
                    pending.extend(successors[after])
                elif reached != start:
                    order.add((start, reached))
    return frozenset(order)


# the jumps a substituted `is None` link turns into, and what may sit between a test and its
# jump, TO_BOOL from 3.13 among them
_TRUTH_TESTS = frozenset({"POP_JUMP_IF_TRUE", "POP_JUMP_IF_FALSE"})
_FLIPPED = {"POP_JUMP_IF_TRUE": "POP_JUMP_IF_FALSE", "POP_JUMP_IF_FALSE": "POP_JUMP_IF_TRUE"}
_BETWEEN = frozenset({"SWAP", "COPY", "NOP", "CACHE", "EXTENDED_ARG", "TO_BOOL"})
# the steps that search `__pyct_identity__(None)`, as a substituted `is None` link compiles
_NONE_LINK = ("__pyct_identity__", None, "CALL", "CONTAINS_OP")


def jump_kind(opname: str, none_link: int | None, *, negated: bool = False) -> str:
    """A conditional jump's kind, a truth test read on the outcome it jumps on.

    ``none_link`` is the argument of the `CONTAINS_OP` right before the jump
    when it searches `__pyct_identity__(None)`, and None for any other jump.
    `x in __pyct_identity__(None)` is true exactly when `x` is None, and
    `not in` exactly when it is not. So `POP_JUMP_IF_TRUE` after `in`, or
    `POP_JUMP_IF_FALSE` after `not in`, jumps when `x` is None, as
    `POP_JUMP_IF_NONE` does, and the other two as `POP_JUMP_IF_NOT_NONE`.

    ``negated`` says the test right before the jump answers a `not in` or an
    `is not`: the operator itself, or pyct's call for one. Such a truth test
    reads as the other one after the operator without its `not`, since it
    jumps on the same outcome. CPython 3.12 folds the `not` of
    ``if not x in c`` into `not in`, and 3.14 keeps `in` with the other
    jump, where pyct's call for `not in` folds it on every release. Every
    other jump keeps its own kind, so a flipped outcome differs.
    """
    if opname not in _TRUTH_TESTS:
        return opname
    if none_link is not None:
        jumps_on_none = (none_link == 0) == (opname == "POP_JUMP_IF_TRUE")
        return "POP_JUMP_IF_NONE" if jumps_on_none else "POP_JUMP_IF_NOT_NONE"
    return _FLIPPED[opname] if negated else opname


def _none_link(steps: list[dis.Instruction], jump: int) -> int | None:
    """The `CONTAINS_OP` argument of a substituted `is None` link the jump tests, or None."""
    if jump < 4:
        return None
    name, constant, call, contains = steps[jump - 4 : jump]
    shape = (name.argval, constant.argval, call.opname, contains.opname)
    loaded = name.opname.startswith("LOAD_") and constant.opname == "LOAD_CONST"
    return contains.arg if loaded and shape == _NONE_LINK else None


# the names of pyct's calls that answer a `not in` or an `is not`
_NEGATIONS = frozenset(name for name, bound in BOUND.items() if bound in ("not_in", "is_not"))


def negations(tree: ast.AST) -> frozenset[Span]:
    """Where each call the substituted tree makes for a `not in` or an `is not` is."""
    return frozenset(
        (node.lineno, node.end_lineno, node.col_offset, node.end_col_offset)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _NEGATIONS
    )


def _negated(steps: list[dis.Instruction], jump: int, negations: frozenset[Span]) -> bool:
    """Whether the test the jump follows answers a `not in` or an `is not`."""
    if jump < 1:
        return False
    test = steps[jump - 1]
    if test.opname in ("CONTAINS_OP", "IS_OP"):
        return test.arg == 1
    return test.opname == "CALL" and tuple(test.positions or ()) in negations


def conditional_jumps(
    code: types.CodeType, negations: frozenset[Span] = frozenset()
) -> list[tuple[object, int | None, str]]:
    """Each conditional jump's position, the line it jumps to and its kind, every copy kept.

    ``negations`` places pyct's calls for a `not in` or an `is not`, in code
    substituted. CPython writes a ``finally`` body twice, once for each way
    out of the ``try``, so two copies of one jump are two entries, and a code
    that drops one differs.
    """
    every = list(dis.get_instructions(code))
    lines = {step.offset: _line(step) for step in every}
    steps = [step for step in every if step.opname not in _BETWEEN]
    return sorted(
        (
            (
                step.positions,
                lines.get(step.argval),
                jump_kind(
                    step.opname,
                    _none_link(steps, at),
                    negated=_negated(steps, at, negations),
                ),
            )
            for at, step in enumerate(steps)
            if step.opname.startswith("POP_JUMP_IF")
        ),
        key=repr,
    )


def layout(code: types.CodeType, negations: frozenset[Span] = frozenset()) -> list[Layout]:
    """What a line tracer and a branch read off each code object: name, lines, steps, jumps.

    ``negations`` places pyct's calls for a `not in` or an `is not`, in code substituted.
    """
    return [
        (
            each.co_name,
            frozenset(line for _, _, line in each.co_lines() if line),
            line_order(each),
            conditional_jumps(each, negations),
        )
        for each in code_objects(code)
    ]


def lined_up(source: str, name: str) -> bool:
    """Whether the source compiled as written and as pyct substitutes it lines up."""
    written = compile(source, name, "exec")
    tree = substitute(ast.parse(source))
    return layout(written) == layout(compile(tree, name, "exec"), negations(tree))
