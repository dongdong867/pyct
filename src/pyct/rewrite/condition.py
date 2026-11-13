"""The model's reply read as one condition, and rewrites' form check of it.

A rewrite is one Python expression on the target's parameters. pyct writes
it into a function of its own, ``__rewrite__``, which hands its value to a
second, ``__held__``, that branches on it, so the fork at that branch's line
is the rewrite's own and every fork the expression itself records sits on a
line of ``__rewrite__``. The check reads the parsed tree before anything runs and refuses a
rewrite outside the form ``FORM`` gives the model; otherwise ``and``,
``or`` and ``not``, and a chained compare, are written as ``&``, ``|`` and
``^ True`` on bools, so the expression records no fork of its own for them.
`pyct.intercept.model_code` then compiles it under the target's
substitutions, and it runs only in a forked child (`pyct.run.model_runs`).

A rewrite reads no parameter that holds an object (``holds_object``): the
check refuses one that names such a parameter, and ``__rewrite__`` does not
take it, so the child is handed plain values alone.
"""

from __future__ import annotations

import ast
import math
import re
import types
from collections.abc import Iterable, Sequence

from pyct.binding.builds import object_form
from pyct.intercept.model_code import Refused, compile_model_code

# the function pyct writes the rewrite into, and the one it branches on the rewrite's value in
FUNCTION = "__rewrite__"
_BRANCH = "__held__"
# the line and column of that branch, whose fork is the rewrite's own
HELD_LINE = 5
HELD_COL = 7
# the characters a rewrite may take, and how deep its expression may nest
MOST_CHARACTERS = 2_000
MOST_DEPTH = 100
# the functions a rewrite may call by name
CALLS = frozenset({"len", "int", "float", "str", "bool", "abs", "min", "max", "ord", "chr"})
# what a rewrite may read, as the request's answer form says it
FORM = (
    "Answer with one Python expression and nothing else: a condition on the function's"
    " parameters that every input it holds for takes the side the line needs. It may be"
    " narrower than the condition. It may read the parameters that hold no object, and their"
    ' items, written x[i] or d["k"]; literals; comparisons; and, or, not; arithmetic; len,'
    " int, float, str, bool, abs, min, max, ord and chr; math.<function>; and the methods of"
    " the values whose names do not start with _, other than format and format_map. It reads"
    " no other name, and no self, and passes no key function. Each operand of and, or and not"
    " runs on every input, so an operand may not raise where an earlier one would have guarded"
    " it."
)
# the methods whose text reads a value's attributes
_READS_FIELDS = frozenset({"format", "format_map"})
# why a reply gives no rewrite
NO_EXPRESSION = "the reply holds no expression"

_FENCE = re.compile(r"```[A-Za-z]*\n(.*?)```", re.DOTALL)
# what the parser raises on text it refuses, a reply too deep for it included
_REFUSALS = (SyntaxError, ValueError, RecursionError, MemoryError)
_CONSTANTS = (int, float, str, bool, type(None))
# the types of the values a rewrite may read, and of those it may read into
_SCALARS = frozenset({type(None), bool, int, float, str})
_HOLDERS = frozenset({list, tuple, dict})
_PLAIN = (ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Tuple, ast.List, ast.Slice)
_REFUSED_AS: dict[type[ast.AST], str] = {
    ast.Lambda: "a lambda",
    ast.IfExp: "an if expression",
    ast.NamedExpr: "an assignment",
    ast.ListComp: "a comprehension",
    ast.SetComp: "a comprehension",
    ast.DictComp: "a comprehension",
    ast.GeneratorExp: "a comprehension",
    ast.Starred: "a star",
}


def expression_in(text: str, parameters: Sequence[str]) -> str | None:
    """The one expression the reply holds: the text of its first code fence, or the whole reply,
    stripped, as Python writes it on one line when it spans lines or holds a character a
    terminal reads. None when that is not one Python expression, or names none of
    ``parameters``, as prose such as ``this is not code`` that parses as Python but is not
    about the function."""
    fenced = _FENCE.search(text)
    body = (fenced.group(1) if fenced else text).strip()
    if not body:
        return None
    try:
        tree = ast.parse(body, mode="eval")
    except _REFUSALS:
        return None
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    if not names & set(parameters):
        return None
    if body.isprintable():
        return body
    try:
        return ast.unparse(tree)
    except RecursionError:
        # too deep to write again; the form check refuses it for its depth
        return body


def rewrite_code(
    expression: str, parameters: Sequence[str], file: str, objects: Sequence[str] = ()
) -> types.CodeType | Refused:
    """The module code of ``__rewrite__`` on ``parameters`` but ``objects``, those that hold an
    object, which branches on ``expression``, each code object named ``file``; or why the
    rewrite is refused.

    ``expression`` is one that ``expression_in`` read, so it sits inside parentheses of its
    own and cannot reach past them.
    """
    if len(expression) > MOST_CHARACTERS:
        return Refused(f"the rewrite is longer than {MOST_CHARACTERS:,} characters")
    readable = [name for name in parameters if name not in objects]
    text = (
        "import math\n\n\n"
        f"def {_BRANCH}(held):\n    if held:\n        return True\n    return False\n\n\n"
        f"def {FUNCTION}({', '.join(readable)}):\n"
        f"    return {_BRANCH}((\n{expression}\n    ))\n"
    )
    return compile_model_code(text, file, _Check(frozenset(parameters), frozenset(objects)))


def holds_object(value: object) -> bool:
    """Whether a value is an object or holds one among the keys and items of its lists, tuples
    and dicts, at any depth: a seed's object form, a dict holding ``"__class__"``
    (``object_form``), or a value whose type is not exactly None, bool, int, float, str, list,
    tuple or dict. Read in a loop, each list, tuple and dict once."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        each = pending.pop()
        kind = type(each)
        if kind in _SCALARS:
            continue
        if kind not in _HOLDERS or object_form(each):
            return True
        if id(each) not in seen:
            seen.add(id(each))
            pending.extend(_held(each))
    return False


def _held(holder: object) -> Iterable[object]:
    """A list's or tuple's items, or a dict's keys and values."""
    if isinstance(holder, dict):
        return [*holder.keys(), *holder.values()]
    assert isinstance(holder, list | tuple)
    return holder


class _Check:
    """Rewrites' form check, which ``compile_model_code`` calls on the parsed module."""

    def __init__(self, parameters: frozenset[str], objects: frozenset[str]) -> None:
        self.parameters = parameters
        self.objects = objects

    def __call__(self, tree: ast.Module) -> ast.Module | str:
        function = tree.body[2]
        assert isinstance(function, ast.FunctionDef)
        returned = function.body[0]
        assert isinstance(returned, ast.Return) and isinstance(returned.value, ast.Call)
        branched = returned.value
        refused = _refusal(branched.args[0], self.parameters, self.objects)
        if refused is not None:
            return refused
        branched.args[0] = _AsBits().visit(branched.args[0])
        return tree


def _refusal(
    expression: ast.expr, parameters: frozenset[str], objects: frozenset[str]
) -> str | None:
    """Why the expression is outside the form, or reads one of ``objects``, the parameters
    that hold an object; or None. Read in a loop, not a call per level."""
    pending: list[tuple[ast.AST, int]] = [(expression, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > MOST_DEPTH:
            return f"the rewrite nests more than {MOST_DEPTH} deep"
        if isinstance(node, ast.Name):
            if node.id in objects:
                return f"a rewrite may not read {node.id}, which holds an object"
            if node.id not in parameters:
                return f"a rewrite may not read {node.id}"
            continue
        found = _parts(node, parameters)
        if isinstance(found, str):
            return found
        pending.extend((part, depth + 1) for part in found)
    return None


def _parts(node: ast.AST, parameters: frozenset[str]) -> list[ast.AST] | str:
    """The parts of one node the check reads next, or why the node is refused."""
    if isinstance(node, ast.Constant):
        return [] if isinstance(node.value, _CONSTANTS) else "a rewrite may not use that literal"
    if isinstance(node, ast.Call):
        return _call_parts(node, parameters)
    if isinstance(node, ast.Subscript):
        return [node.value, node.slice]
    if isinstance(node, _PLAIN):
        return [part for part in ast.iter_child_nodes(node) if isinstance(part, ast.expr)]
    if isinstance(node, ast.Attribute):
        return f"a rewrite may not read the attribute {node.attr}"
    return f"a rewrite may not use {_REFUSED_AS.get(type(node), type(node).__name__)}"


def _call_parts(call: ast.Call, parameters: frozenset[str]) -> list[ast.AST] | str:
    """A call's arguments, and a method's receiver, or why the call is refused: a function not
    in ``CALLS``, a method that starts with ``_`` or reads fields from its text, a ``math``
    name it has no function for, an argument unpacked with ``*`` or ``**``, or a key
    function."""
    parts: list[ast.AST] = [*call.args, *(keyword.value for keyword in call.keywords)]
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    ):
        return "a rewrite may not unpack arguments"
    if any(keyword.arg == "key" for keyword in call.keywords):
        return "a rewrite may not pass a key function"
    func = call.func
    if isinstance(func, ast.Name):
        allowed = func.id in CALLS and func.id not in parameters
        return parts if allowed else f"a rewrite may not call {func.id}"
    if not isinstance(func, ast.Attribute):
        return "a rewrite calls only a function by its name or a method"
    if func.attr.startswith("_") or func.attr in _READS_FIELDS:
        return f"a rewrite may not call {func.attr}"
    receiver = func.value
    if isinstance(receiver, ast.Name) and receiver.id == "math" and "math" not in parameters:
        if not callable(getattr(math, func.attr, None)):
            return f"math has no function {func.attr}"
        return parts
    return [receiver, *parts]


class _AsBits(ast.NodeTransformer):
    """``and``, ``or``, ``not`` and a chained compare written as ``&``, ``|``, ``^ True`` and
    ``&`` on bools. The check has bounded the depth, so a call per level is safe."""

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.expr:
        values = [_as_bool(self.visit(value)) for value in node.values]
        op: ast.operator = ast.BitAnd() if isinstance(node.op, ast.And) else ast.BitOr()
        joined = values[0]
        for value in values[1:]:
            joined = ast.BinOp(joined, op, value)
        return ast.copy_location(joined, node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.expr:
        self.generic_visit(node)
        if not isinstance(node.op, ast.Not):
            return node
        flipped = ast.BinOp(_as_bool(node.operand), ast.BitXor(), ast.Constant(True))
        return ast.copy_location(flipped, node)

    def visit_Compare(self, node: ast.Compare) -> ast.expr:
        self.generic_visit(node)
        if len(node.ops) == 1:
            return node
        operands = [node.left, *node.comparators]
        pairs = [
            ast.Compare(operands[at], [op], [operands[at + 1]]) for at, op in enumerate(node.ops)
        ]
        joined: ast.expr = pairs[0]
        for pair in pairs[1:]:
            joined = ast.BinOp(joined, ast.BitAnd(), pair)
        return ast.copy_location(joined, node)


def _as_bool(value: ast.expr) -> ast.expr:
    return ast.copy_location(ast.Call(ast.Name("bool", ast.Load()), [value], []), value)
