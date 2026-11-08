"""The calls pyct watches where the target writes them, for an answer that lost a tracked value.

A call ``f(a, b)`` becomes ``__pyct_answer__(f(__pyct_first__(a),
__pyct_given__(b)), "f")`` (`pyct.core.entry.watch`): the callee and each
argument are the call's own nodes, kept in place, so each is evaluated once
and in Python's order, and the callee is called from the target's frame. The
text is the callee as the call writes it, which names the downgrade a loss
records. A constant after the first argument passes as written.

A call is watched when its arguments are written out (`calls.written_out`),
at least one is not a constant, and it calls a function pyct leaves to
Python: no other rule substitutes it, as each router there records its own
losses, its callee is none of pyct's names nor a bare name pyct binds in
the module's builtins (`pyct.core.entry.bound.BOUND`), and it is not written
``isinstance(...)``, ``callable(...)`` or ``hasattr(...)``, bare or after a
dot, whose answer is read off a value's type. A call whose arguments hold an
``await`` or a ``yield`` stays as written too: its frame can stop between
the call's first argument and its answer while another frame's calls run.
"""

from __future__ import annotations

import ast

from pyct.core.entry.bound import BOUND as BOUND_BUILTINS
from pyct.intercept.calls import spelled, written_out
from pyct.intercept.positions import Parts, after_the_value

BOUND: dict[str, str] = {
    "__pyct_first__": "first",
    "__pyct_given__": "given",
    "__pyct_answer__": "answer",
}

# the names of the builtins whose answer is read off a value's type, never off the value
_BY_TYPE = frozenset({"isinstance", "callable", "hasattr"})
# the nodes that can stop a frame part way through a call's arguments
_STOPS = (ast.Await, ast.Yield, ast.YieldFrom)


def watched(call: ast.Call, parts: Parts, reserved: frozenset[str]) -> ast.Call:
    """The call that watches ``call``, as the target wrote it, or ``call`` itself when it is not
    one to watch."""
    if not _watchable(call, reserved) or spelled(call.func) in _BY_TYPE:
        return call
    count = len(call.args)
    arguments = _arguments(call)
    # what CPython runs after each argument: the next one's first instruction, or the call
    after = [parts.first(each) for each in arguments[1:]] + [call]
    passed = [
        _passed(argument, parts, first=index == 0, then=after[index])
        for index, argument in enumerate(arguments)
    ]
    for keyword, value in zip(call.keywords, passed[count:], strict=True):
        keyword.value = value
    call.args = passed[:count]
    text = ast.copy_location(ast.Constant(value=ast.unparse(call.func)), call)
    outer = ast.Call(func=parts.named("__pyct_answer__", call), args=[call, text], keywords=[])
    return ast.copy_location(outer, call)


def answered(node: ast.AST) -> bool:
    """Whether a node is a call this rule made around a call it watches."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__pyct_answer__"
    )


def _arguments(call: ast.Call) -> list[ast.expr]:
    """A call's arguments in the order Python evaluates them: by position, then by keyword."""
    return [*call.args, *(keyword.value for keyword in call.keywords)]


def _watchable(call: ast.Call, reserved: frozenset[str]) -> bool:
    """Whether a call is written out with an argument other than a constant, its callee is not
    pyct's, and no argument can stop its frame."""
    if _pyct_s(call.func, reserved):
        return False
    arguments = _arguments(call)
    if not written_out(call) or all(isinstance(each, ast.Constant) for each in arguments):
        return False
    return not any(isinstance(node, _STOPS) for each in arguments for node in ast.walk(each))


def _pyct_s(callee: ast.expr, reserved: frozenset[str]) -> bool:
    """Whether a callee is pyct's: one of its names, a bare name it binds in the module's
    builtins, or a call of one of its names, as a rule's router hands back."""
    if isinstance(callee, ast.Call):
        return isinstance(callee.func, ast.Name) and callee.func.id in reserved
    return isinstance(callee, ast.Name) and (callee.id in reserved or callee.id in BOUND_BUILTINS)


def _passed(argument: ast.expr, parts: Parts, *, first: bool, then: ast.expr) -> ast.expr:
    """The argument as the watch takes it: the first through ``__pyct_first__``, a later one
    through ``__pyct_given__``, and a later constant as written.

    The call sits where the argument's last instruction is, so it adds no
    line step after it, or, after an argument whose jumps land past its last
    instruction, where what comes next, ``then``, starts: the jumps land on
    the call, as they landed there.
    """
    if isinstance(argument, ast.Constant) and not first:
        return argument
    name = "__pyct_first__" if first else "__pyct_given__"
    call = ast.Call(func=parts.named(name, argument), args=[argument], keywords=[])
    if _jumps_past(argument):
        return ast.copy_location(call, then)
    return after_the_value(call, argument)


def _jumps_past(argument: ast.expr) -> bool:
    """Whether an argument's own jumps land past its last instruction: an `and` or `or`, a
    conditional expression, and a chained compare."""
    if isinstance(argument, ast.NamedExpr):
        return False
    chained = isinstance(argument, ast.Compare) and len(argument.ops) > 1
    return chained or isinstance(argument, ast.BoolOp | ast.IfExp)
