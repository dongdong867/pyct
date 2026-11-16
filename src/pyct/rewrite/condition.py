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

``__rewrite__`` takes exactly the parameters the expression names
(``Rewrite.reads``), by keyword into one dict, ``ARGUMENTS``, so the
expression reads each as ``ARGUMENTS["name"]`` and no parameter's name can
stand for a name pyct writes in, ``bool``, ``__held__`` or ``READER``; the
child is handed those arguments, and a kept rewrite is checked against those
names. A parameter that is an object on the input
(``pyct.rewrite.kinds``) is read only as ``name.field``, one level deep: the
check refuses any other use of its name, since using the object whole runs
its class's special methods, and a field whose name starts and ends with
``__``. Each field read is then written as a call of pyct's reader,
``READER``, which the child binds to one that reads only what the instance
stores (``pyct.binding.stored``), so the reply's own tree never names it. A
parameter that holds an object inside a list, tuple or dict is one a rewrite
may not read at all.
"""

from __future__ import annotations

import ast
import math
import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pyct.intercept.model_code import Refused, compile_model_code
from pyct.utils.fences import code_blocks

# the function pyct writes the rewrite into, and the one it branches on the rewrite's value in
FUNCTION = "__rewrite__"
# the name each field read of an object is written as a call of, which the child binds to pyct's
# reader: called with the object, its parameter's name and the field's
READER = "__pyct_field__"
_BRANCH = "__held__"
# the dict ``__rewrite__`` takes its arguments in, by keyword, whatever their names
ARGUMENTS = "arguments"
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
    " narrower than the condition. It may read the parameters, a method's self among them, and"
    ' their items, written x[i] or d["k"]; a field of a parameter that is an object, written'
    " order.code, one level deep, but never the object whole and never its methods; literals;"
    " comparisons; and, or, not; arithmetic; len, int, float, str, bool, abs, min, max, ord and"
    " chr; math.<function>; and the methods of the values whose names do not start with _,"
    " other than format and format_map. It reads no other name, and no parameter that holds an"
    " object inside a list, tuple or dict, and passes no key function. Each operand of and, or"
    " and not runs on every input, so an operand may not raise where an earlier one would have"
    " guarded it."
)
# the methods whose text reads a value's attributes
_READS_FIELDS = frozenset({"format", "format_map"})
# why a reply gives no rewrite
NO_EXPRESSION = "the reply holds no expression"

# what the parser raises on text it refuses, a reply too deep for it included
_REFUSALS = (SyntaxError, ValueError, RecursionError, MemoryError)
# the literals a rewrite may write
LITERALS: tuple[type, ...] = (int, float, str, bool, type(None))
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
    """The one expression the reply holds: the text of its first code fence, read as
    ``pyct.utils.fences`` reads it, or the whole reply, stripped, as Python writes it on one
    line when it spans lines or holds a character a terminal reads. None when that is not one
    Python expression, or names none of ``parameters``, as prose such as ``this is not code``
    that parses as Python but is not about the function."""
    fenced = code_blocks(text)
    body = (fenced[0] if fenced else text).strip()
    if not body:
        return None
    try:
        tree = ast.parse(body, mode="eval")
    except _REFUSALS:
        return None
    if not _names(tree) & set(parameters):
        return None
    if body.isprintable():
        return body
    try:
        return ast.unparse(tree)
    except RecursionError:
        # too deep to write again; the form check refuses it for its depth
        return body


@dataclass(frozen=True)
class Rewrite:
    """A rewrite's module code, and the parameters its expression reads, in the function's
    order: what ``__rewrite__`` takes, what its child is handed, and what a kept rewrite needs
    an input to hold. ``fields`` are the field reads of objects it makes, each written
    ``name.field``, in the order the expression writes them."""

    code: types.CodeType
    reads: tuple[str, ...]
    fields: tuple[str, ...] = ()

    @property
    def objects(self) -> tuple[str, ...]:
        """The parameters it reads fields of, which a kept rewrite needs an input to hold as
        objects."""
        return tuple(dict.fromkeys(field.partition(".")[0] for field in self.fields))

    def handed(self, args: Mapping[str, object]) -> dict[str, object]:
        """The arguments the rewrite reads, taken from ``args``, which holds each of them."""
        return {name: args[name] for name in self.reads}


def rewrite_code(
    expression: str,
    parameters: Sequence[str],
    file: str,
    holders: Sequence[str] = (),
    objects: Sequence[str] = (),
) -> Rewrite | Refused:
    """The module code of ``__rewrite__`` on the ``parameters`` that ``expression`` reads,
    which branches on it, each code object named ``file``; or why the rewrite is refused, one
    reading any of ``holders``, those that hold an object inside a list, tuple or dict,
    included, and one using any of ``objects``, those that are objects, other than as
    ``name.field``.

    ``expression`` is one that ``expression_in`` read, so it sits inside parentheses of its
    own and cannot reach past them.
    """
    if len(expression) > MOST_CHARACTERS:
        return Refused(f"the rewrite is longer than {MOST_CHARACTERS:,} characters")
    reads = _reads(expression, parameters)
    text = (
        "import math\n\n\n"
        f"def {_BRANCH}(held):\n    if held:\n        return True\n    return False\n\n\n"
        f"def {FUNCTION}(**{ARGUMENTS}):\n"
        f"    return {_BRANCH}((\n{expression}\n    ))\n"
    )
    check = _Check(frozenset(parameters), frozenset(holders), frozenset(objects))
    code = compile_model_code(text, file, check)
    return code if isinstance(code, Refused) else Rewrite(code, reads, tuple(check.read))


def _reads(expression: str, parameters: Sequence[str]) -> tuple[str, ...]:
    """The parameters ``expression`` names, in their order; none when it does not parse, as when
    ``expression_in`` wrote it again with more parentheses than the parser takes, such as one
    around each generator handed to a call, which the compile then refuses."""
    try:
        tree = ast.parse(expression, mode="eval")
    except _REFUSALS:
        return ()
    named = _names(tree)
    return tuple(name for name in parameters if name in named)


def _names(tree: ast.AST) -> set[str]:
    """Each name the tree reads or writes."""
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


class _Check:
    """Rewrites' form check, which ``compile_model_code`` calls on the parsed module."""

    def __init__(
        self, parameters: frozenset[str], holders: frozenset[str], objects: frozenset[str]
    ) -> None:
        self.parameters = parameters
        self.holders = holders
        self.objects = objects
        # each field read written as the reader's call, as ``name.field``, once
        self.read: list[str] = []

    def __call__(self, tree: ast.Module) -> ast.Module | str:
        function = tree.body[2]
        assert isinstance(function, ast.FunctionDef)
        returned = function.body[0]
        assert isinstance(returned, ast.Return) and isinstance(returned.value, ast.Call)
        branched = returned.value
        rules = ExpressionRules("rewrite", self.parameters, self.holders, self.objects)
        refused = refusal(branched.args[0], rules)
        if refused is not None:
            return refused
        reads = _AsReads(self.parameters, self.objects)
        branched.args[0] = _AsBits().visit(reads.visit(branched.args[0]))
        self.read = list(dict.fromkeys(reads.read))
        return tree


@dataclass(frozen=True)
class ExpressionRules:
    """What one expression of model-written code may read, call and write: the noun its
    refusals name the code by, the names it may read, the ``holders`` among them it may not
    since each holds an object inside a list, tuple or dict, the ``objects`` it may read only as
    ``name.field`` since each is an object, the functions it may call by name, and the types of
    its literals."""

    noun: str
    names: frozenset[str]
    holders: frozenset[str] = frozenset()
    objects: frozenset[str] = frozenset()
    calls: frozenset[str] = CALLS
    literals: tuple[type, ...] = LITERALS


def refusal(expression: ast.expr, rules: ExpressionRules) -> str | None:
    """Why the expression is outside the form ``rules`` allow, reads one of their ``holders``
    at all, or one of their ``objects`` other than as ``name.field``; or None. A name that holds
    an object is said first, wherever it sits. Read in a loop, not a call per level."""
    held = _holding(expression, rules)
    if held is not None:
        return f"a {rules.noun} may not read {held}, which holds an object"
    pending: list[tuple[ast.AST, int]] = [(expression, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > MOST_DEPTH:
            return f"the {rules.noun} nests more than {MOST_DEPTH} deep"
        if isinstance(node, ast.Name):
            if node.id in rules.objects:
                return f"a {rules.noun} may read {node.id} only as {node.id}.<field>"
            if node.id not in rules.names:
                return f"a {rules.noun} may not read {node.id}"
            continue
        found = _parts(node, rules)
        if isinstance(found, str):
            return found
        pending.extend((part, depth + 1) for part in found)
    return None


def _parts(node: ast.AST, rules: ExpressionRules) -> list[ast.AST] | str:
    """The parts of one node the check reads next, or why the node is refused."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, rules.literals):
            return []
        return f"a {rules.noun} may not use that literal"
    if isinstance(node, ast.Call):
        return _call_parts(node, rules)
    if isinstance(node, ast.Subscript):
        return [node.value, node.slice]
    if isinstance(node, _PLAIN):
        return [part for part in ast.iter_child_nodes(node) if isinstance(part, ast.expr)]
    if isinstance(node, ast.Attribute) and _field(node, rules) and not _special(node.attr):
        return []
    if isinstance(node, ast.Attribute):
        return f"a {rules.noun} may not read the attribute {node.attr}"
    return f"a {rules.noun} may not use {_REFUSED_AS.get(type(node), type(node).__name__)}"


def _call_parts(call: ast.Call, rules: ExpressionRules) -> list[ast.AST] | str:
    """A call's arguments, and a method's receiver, or why the call is refused: a function not
    in the rules' ``calls``, a method that starts with ``_`` or reads fields from its text, a
    ``math`` name it has no function for, an argument unpacked with ``*`` or ``**``, or a key
    function."""
    noun = rules.noun
    parts: list[ast.AST] = [*call.args, *(keyword.value for keyword in call.keywords)]
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    ):
        return f"a {noun} may not unpack arguments"
    if any(keyword.arg == "key" for keyword in call.keywords):
        return f"a {noun} may not pass a key function"
    func = call.func
    if isinstance(func, ast.Name):
        allowed = func.id in rules.calls and func.id not in rules.names
        return parts if allowed else f"a {noun} may not call {func.id}"
    if not isinstance(func, ast.Attribute):
        return f"a {noun} calls only a function by its name or a method"
    if isinstance(func.value, ast.Name) and func.value.id in rules.objects:
        return f"a {noun} may not call a method of {func.value.id}"
    if func.attr.startswith("_") or func.attr in _READS_FIELDS:
        return f"a {noun} may not call {func.attr}"
    receiver = func.value
    if isinstance(receiver, ast.Name) and receiver.id == "math" and "math" not in rules.names:
        if not callable(getattr(math, func.attr, None)):
            return f"math has no function {func.attr}"
        return parts
    return [receiver, *parts]


def _holding(expression: ast.expr, rules: ExpressionRules) -> str | None:
    """The first name the expression reads that holds an object inside a list, tuple or dict,
    one of the rules' ``holders``, or None."""
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and node.id in rules.holders:
            return node.id
    return None


def _field(node: ast.Attribute, rules: ExpressionRules) -> bool:
    """Whether the attribute reads a field of one of the rules' ``objects``, written
    ``name.field``; whether that field's name is allowed is the caller's to check."""
    return isinstance(node.value, ast.Name) and node.value.id in rules.objects


def _special(name: str) -> bool:
    """Whether the name starts and ends with ``__``, as Python's own special names do."""
    return name.startswith("__") and name.endswith("__")


class _AsReads(ast.NodeTransformer):
    """Each of ``parameters`` written as its entry of ``ARGUMENTS``, and each field read of one
    of ``objects``, ``name.field``, as the reader's call, ``READER(ARGUMENTS["name"], "name",
    "field")``, kept in ``read`` as ``name.field``. The check has bounded the depth, so a call
    per level is safe."""

    def __init__(self, parameters: frozenset[str], objects: frozenset[str]) -> None:
        self.parameters = parameters
        self.objects = objects
        self.read: list[str] = []

    def visit_Name(self, node: ast.Name) -> ast.expr:
        if node.id not in self.parameters:
            return node
        return ast.copy_location(_argument(node.id), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        value = node.value
        if not isinstance(value, ast.Name) or value.id not in self.objects:
            self.generic_visit(node)
            return node
        self.read.append(f"{value.id}.{node.attr}")
        reader_args: list[ast.expr] = [
            ast.copy_location(_argument(value.id), value),
            ast.Constant(value.id),
            ast.Constant(node.attr),
        ]
        return ast.copy_location(ast.Call(ast.Name(READER, ast.Load()), reader_args, []), node)


def _argument(name: str) -> ast.expr:
    """The parameter ``name`` read from ``ARGUMENTS``."""
    return ast.Subscript(ast.Name(ARGUMENTS, ast.Load()), ast.Constant(name), ast.Load())


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
