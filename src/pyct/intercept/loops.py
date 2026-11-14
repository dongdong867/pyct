"""The hooks pyct writes around each piece of a function, when the interception's pieces switch is
on: a loop, and an assignment of a comprehension (`pyct.results.pieces`).

Each hook is a call of a function of `pyct.core.entry.pieces` through a name
the module binds, given the piece's site and names as constants: its line,
its column, the names going in and the changed names. The hook reads the
file from the caller's code.

- A ``for`` or ``async for`` hands its iterable to ``__pyct_piece_over__``,
  which hands it back: ``for x in __pyct_piece_over__(xs, 3, 4, ("xs",),
  ("t",)):``.
- A ``while`` starts with a ``__pyct_piece_in__(...)`` statement before it,
  placed at its test's first instruction.
- A loop ends with a ``__pyct_piece_out__(...)`` statement: at the start of
  its ``else``, added when it has none, and before each ``break`` that leaves
  it, on that ``break``'s line. The ``else`` of a ``for`` holds it where its
  iterable starts, where CPython ends the loop. That of a ``while`` holds it
  where its test's false outcome jumps to in the module as written, which a
  probe compile of the module reads, once per module with a ``while``. A
  ``while`` whose test is a true constant, as ``while True``, gets the
  ``break`` hooks alone. A loop that ends by ``return`` or a raise calls no
  exit hook.
- An assignment ``t = value`` becomes ``t = __pyct_piece_value__(
  __pyct_piece_in__(...), value)``: the entry runs before the value, and the
  exit takes the entry's token and hands the value back.

Each call sits where the instructions it stands beside already are, so the
module's lines, the steps between them and its conditional jumps stay as
written (the suite's lines-up check). Three kinds of ``while`` are left as
written, with no hooks, since no place for the exit hook lines up for them:
one that is the last statement of another loop's body, directly or as the
last statement of an ``if`` that is, where CPython turns its test into a
jump back into its body; one whose test's false outcome lands, in the
module as written, on more than one line, or on a jump with no line of its
own; and one whose test is a chained compare. The second takes in a
``while`` whose test, on a line apart from its body, holds a
comprehension's or a generator expression's own condition, as ``while
any(x for x in xs if x > n):``: the probe reads that condition's jumps as
false outcomes on the test's line, beside the one past the loop. A loop at
module level or in a class body is no piece, and gets no hooks either.

A piece with no changed name is left as written too: a summary gives a
formula for each changed name, so such a piece has nothing to record.
"""

from __future__ import annotations

import ast
import dis
import types
import warnings
from collections.abc import Iterator

from pyct.intercept.positions import Parts, after_the_value
from pyct.intercept.watch import jumps_past
from pyct.results.pieces import FUNCTIONS, SCOPES, Piece, pieces
from pyct.results.sources import LOOPS

_OVER = "__pyct_piece_over__"
_IN = "__pyct_piece_in__"
_OUT = "__pyct_piece_out__"
_VALUE = "__pyct_piece_value__"
# the module that defines the hooks, which a module binds them from, so one compiled with the
# switch off never loads it
HOOKS = "pyct.core.entry.pieces"
BOUND: dict[str, str] = {
    _OVER: "piece_over",
    _IN: "piece_in",
    _OUT: "piece_out",
    _VALUE: "piece_value",
}

# the line and column of an instruction with none
_NO_LINE = -1
# the jumps that take control on without a test
_HOPS = frozenset(
    {"JUMP_FORWARD", "JUMP_BACKWARD", "JUMP", "JUMP_NO_INTERRUPT", "JUMP_BACKWARD_NO_INTERRUPT"}
)
# the instructions a landing in a `while`'s test can pass on by without evaluating anything
_PASSING = _HOPS | {"NOP"}

# a place in the source, as `dis` gives an instruction's: line, last line, column, last column
type _Span = tuple[int | None, int | None, int | None, int | None]
# where each conditional jump of the module as written can send control, each copy of it apart,
# by the jump's place
type _Landings = dict[_Span, list[list[dis.Instruction]]]
# the owner of each statement, and the list of statements it is in
type _Owners = dict[int, tuple[ast.AST, list[ast.stmt]]]


def hooked(tree: ast.Module, parts: Parts) -> None:
    """Write each piece of each function in the tree with its hooks, in place.

    Which pieces get hooks, and where each hook goes, is worked out from
    the tree as written, before the first hook goes in.
    """
    found = [
        (statement, piece)
        for node in ast.walk(tree)
        if isinstance(node, FUNCTIONS)
        for statement, piece in pieces(node)
        if piece.changed
    ]
    whiles = [statement for statement, _ in found if isinstance(statement, ast.While)]
    owners = _owners(tree) if whiles else {}
    landings = _landings(tree) if whiles else {}
    left = {id(each) for each in whiles if _left_as_written(each, owners, landings, parts)}
    planned = [
        (statement, piece, _exit_place(statement, landings, parts))
        for statement, piece in found
        if id(statement) not in left
    ]
    for statement, piece, exit_place in planned:
        if isinstance(statement, ast.While):
            _hook_while(statement, piece, exit_place, owners, parts)
        elif isinstance(statement, ast.For | ast.AsyncFor):
            _hook_for(statement, piece, exit_place, parts)
        elif isinstance(statement, ast.Assign | ast.AnnAssign):
            _hook_value(statement, piece, parts)


def _exit_place(statement: ast.stmt, landings: _Landings, parts: Parts) -> tuple[int, int] | None:
    """Where a loop's ``else`` holds its exit hook, or None when it holds none."""
    if isinstance(statement, ast.For | ast.AsyncFor):
        return statement.iter.lineno, statement.iter.col_offset
    if isinstance(statement, ast.While):
        return _while_exit(statement, landings, parts)
    return None


def _hook_for(
    loop: ast.For | ast.AsyncFor, piece: Piece, exit_place: tuple[int, int] | None, parts: Parts
) -> None:
    """Hand the loop's iterable to the entry hook, and end it with the exit hook."""
    iterable = loop.iter
    site = _site(piece)
    entry = ast.Call(func=parts.named(_OVER, iterable), args=[iterable, *site], keywords=[])
    loop.iter = after_the_value(entry, iterable)
    for constant in site:
        ast.copy_location(constant, entry)
    _hook_exits(loop, piece, exit_place)


def _hook_while(
    loop: ast.While,
    piece: Piece,
    exit_place: tuple[int, int] | None,
    owners: _Owners,
    parts: Parts,
) -> None:
    """Start the loop with the entry hook, at its test's first instruction, and end it with the
    exit hook."""
    first = parts.first(loop.test)
    entry = _placed(ast.Expr(value=_called(_IN, _site(piece))), first.lineno, first.col_offset)
    _, statements = owners[id(loop)]
    statements.insert(_index(statements, loop), entry)
    _hook_exits(loop, piece, exit_place)


def _hook_exits(
    loop: ast.For | ast.AsyncFor | ast.While, piece: Piece, exit_place: tuple[int, int] | None
) -> None:
    """The exit hook at the start of the loop's ``else``, when it holds one, and before each
    ``break`` that leaves the loop."""
    if exit_place is not None:
        loop.orelse.insert(0, exit_statement(piece, *exit_place))
    for statements, leaving in _breaks(loop):
        hook = exit_statement(piece, leaving.lineno, leaving.col_offset)
        statements.insert(_index(statements, leaving), hook)


def exit_statement(piece: Piece, line: int, column: int) -> ast.stmt:
    """The statement a loop's run ends with, placed at one spot: a call of the exit hook, whose
    answer it drops."""
    return _placed(ast.Expr(value=_called(_OUT, _site(piece))), line, column)


def _hook_value(statement: ast.Assign | ast.AnnAssign, piece: Piece, parts: Parts) -> None:
    """Hand the assignment's value to the exit hook, after the entry hook's token.

    The entry sits where the value's first instruction is, and the exit's
    call where the value's last instruction is, or, after a value whose
    jumps land past its last instruction, where the store into the target is.
    """
    value = statement.value
    if value is None:
        return
    first = parts.first(value)
    entry = _placed(_called(_IN, _site(piece)), first.lineno, first.col_offset)
    exit_call = ast.Call(func=parts.named(_VALUE, value), args=[entry, value], keywords=[])
    statement.value = after_the_value(exit_call, value)
    if jumps_past(value):
        target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
        ast.copy_location(exit_call, target)


def _site(piece: Piece) -> list[ast.expr]:
    """The constants each hook of a piece is given: its line, column, names going in and changed
    names."""
    values = (piece.line, piece.col, piece.going_in, piece.changed)
    # a Constant holds a tuple of constants too, which typeshed leaves out
    return [ast.Constant(value=value) for value in values]  # pyrefly: ignore[bad-argument-type]


def _called(name: str, arguments: list[ast.expr]) -> ast.Call:
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=arguments, keywords=[])


def _placed[Placed: ast.AST](node: Placed, line: int, column: int) -> Placed:
    """The node, and every part of it, placed at one line and column, taking no room of its own."""
    for each in ast.walk(node):
        if isinstance(each, ast.expr | ast.stmt):
            each.lineno = each.end_lineno = line
            each.col_offset = each.end_col_offset = column
    return node


def _index(statements: list[ast.stmt], statement: ast.stmt) -> int:
    return next(index for index, each in enumerate(statements) if each is statement)


def _owners(tree: ast.Module) -> _Owners:
    """Each statement's owner and the list of statements it is in."""
    owners: _Owners = {}
    for node in ast.walk(tree):
        for _, value in ast.iter_fields(node):
            if isinstance(value, list):
                for each in value:
                    if isinstance(each, ast.stmt):
                        owners[id(each)] = (node, value)
    return owners


def _left_as_written(loop: ast.While, owners: _Owners, landings: _Landings, parts: Parts) -> bool:
    """Whether a ``while`` is left with no hooks: its test is a chained compare, its test's false
    outcomes land on more than one line or on a jump with no line, or it is the last statement
    of another loop's body, directly or through the ``if`` it ends."""
    test = loop.test
    if isinstance(test, ast.Compare) and len(test.ops) > 1:
        return True
    outcomes = _false_outcomes(loop, landings, parts)
    if len({line for (line, _), _ in outcomes}) > 1:
        return True
    if any(line == _NO_LINE and step.opname in _HOPS for (line, _), step in outcomes):
        return True
    return _ends_a_loop_body(loop, owners)


def _ends_a_loop_body(loop: ast.While, owners: _Owners) -> bool:
    """Whether a ``while`` is the last statement of another loop's body, directly or through the
    ``if`` it ends."""
    statement: ast.stmt = loop
    while True:
        owner, statements = owners[id(statement)]
        if statements[-1] is not statement:
            return False
        if isinstance(owner, LOOPS):
            return statements is owner.body
        if not isinstance(owner, ast.If):
            return False
        statement = owner


def _breaks(loop: ast.For | ast.AsyncFor | ast.While) -> list[tuple[list[ast.stmt], ast.Break]]:
    """Each ``break`` that leaves the loop, with the statements it is in: in its body, at any
    depth, a nested loop's ``else`` included, but not a nested loop's body or a scope's."""
    found: list[tuple[list[ast.stmt], ast.Break]] = []
    pending: list[list[ast.stmt]] = [loop.body]
    while pending:
        statements = pending.pop()
        for each in statements:
            if isinstance(each, ast.Break):
                found.append((statements, each))
            elif isinstance(each, LOOPS):
                pending.append(each.orelse)
            elif not isinstance(each, SCOPES):
                pending.extend(_statement_lists(each))
    return found


def _statement_lists(statement: ast.stmt) -> Iterator[list[ast.stmt]]:
    """The lists of statements a statement holds: its own, and its handlers' and cases'."""
    for _, value in ast.iter_fields(statement):
        if not isinstance(value, list):
            continue
        for each in value:
            if isinstance(each, ast.ExceptHandler | ast.match_case):
                yield each.body
        if value and isinstance(value[0], ast.stmt):
            yield value


def _landings(tree: ast.Module) -> _Landings:
    """Where each conditional jump of the module as written can send control: its target, and
    the instruction after a jump if true, read from a probe compile. Nothing when the module
    does not compile, which its own compile then says."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            code = compile(tree, "<pyct probe>", "exec", dont_inherit=True)
    except (SyntaxError, ValueError):
        return {}
    found: _Landings = {}
    for each in _code_objects(code):
        steps = list(dis.get_instructions(each))
        at = {step.offset: index for index, step in enumerate(steps)}
        for index, step in enumerate(steps):
            if step.opname.startswith("POP_JUMP_IF") and step.argval in at:
                lands = [steps[at[step.argval]]]
                if step.opname == "POP_JUMP_IF_TRUE" and index + 1 < len(steps):
                    lands.append(_after(steps, index))
                found.setdefault(_span(step), []).append(lands)
    return found


def _span(step: dis.Instruction) -> _Span:
    where = step.positions
    if where is None:
        return None, None, None, None
    return where.lineno, where.end_lineno, where.col_offset, where.end_col_offset


def _after(steps: list[dis.Instruction], index: int) -> dis.Instruction:
    """The instruction control falls through to after a jump: past a NOT_TAKEN, from 3.14."""
    after = steps[index + 1]
    return steps[index + 2] if after.opname == "NOT_TAKEN" else after


def _code_objects(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _code_objects(constant)


def _while_exit(loop: ast.While, landings: _Landings, parts: Parts) -> tuple[int, int] | None:
    """Where a ``while``'s ``else`` holds its exit hook: where its test's false outcome first lands
    in the module as written, else the test's own start; None for a test that is a true
    constant."""
    test = loop.test
    if isinstance(test, ast.Constant) and test.value:
        return None
    outcomes = _false_outcomes(loop, landings, parts)
    return outcomes[0][0] if outcomes else (test.lineno, test.col_offset)


def _false_outcomes(
    loop: ast.While, landings: _Landings, parts: Parts
) -> list[tuple[tuple[int, int], dis.Instruction]]:
    """Where each conditional jump in a ``while``'s test lands on its false outcome in the module
    as written, CPython writing the test both before the body and after it: the landing's place,
    or the test's own start for a landing inside the test, and the instruction it lands on.

    A landing in the loop's body, or on the first instruction of a later
    operand of an `and`, `or` or conditional expression in the test, is the
    test going on, not its false outcome; a jump or a NOP CPython places at
    such an operand, on its way out of the loop, is not. A landing with no
    line is at `_NO_LINE`.
    """
    test = loop.test
    start = (test.lineno, test.col_offset)
    end = (test.end_lineno or test.lineno, test.end_col_offset or test.col_offset)
    body = range(loop.body[0].lineno, (loop.body[-1].end_lineno or loop.body[-1].lineno) + 1)
    going_on = _test_parts(test, parts)
    found: list[tuple[tuple[int, int], dis.Instruction]] = []
    for (line, last, column, last_column), copies in landings.items():
        if line is None or not (start <= (line, column) and (last, last_column) <= end):  # pyrefly: ignore[unsupported-operation]
            continue
        for lands in copies:
            for landing in lands:
                at = _place(landing)
                if (landing.opname in _PASSING or at not in going_on) and at[0] not in body:
                    found.append((start if start <= at < end else at, landing))
                    break
    return found


def _place(step: dis.Instruction) -> tuple[int, int]:
    """An instruction's line and column, or `_NO_LINE` for each when it has no line."""
    where = step.positions
    if where is None or where.lineno is None:
        return _NO_LINE, _NO_LINE
    return where.lineno, where.col_offset or 0


def _test_parts(test: ast.expr, parts: Parts) -> set[tuple[int, int]]:
    """Where each later operand of an `and` or `or`, and each branch of a conditional expression,
    in the test starts."""
    starts: set[tuple[int, int]] = set()
    for node in ast.walk(test):
        if isinstance(node, ast.BoolOp):
            later = node.values[1:]
        elif isinstance(node, ast.IfExp):
            later = [node.body, node.orelse]
        else:
            continue
        for each in later:
            first = parts.first(each)
            starts.add((first.lineno, first.col_offset))
    return starts
