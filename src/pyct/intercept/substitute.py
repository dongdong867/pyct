"""The operations pyct substitutes where the target writes them.

The compares with `is` and `in` are here, in three shapes, each a compare
with one operator:

- ``a is True``, ``a is not False``, ``True is a``: `is` or `is not` with
  the constant True or False on one side;
- ``a in b`` and ``a not in b``;
- ``not`` over one of those, folded into the other operator as CPython's
  optimizer folds it, so ``not (a in b)`` is ``a not in b``.

Each becomes a call of a function of `pyct.core.substitutes` through a
dunder name, ``__pyct_in__(a, b)`` say. The operands are the compare's own
nodes, moved into the call and never copied, so each is evaluated once and
in Python's order: the left, then the right, then the test.

The module binds those names itself, in an import placed before its first
statement that runs code, after its docstring and its ``__future__``
imports and at that statement's first instruction
(`positions.statement_start`), so it adds no line and the code has them in
whatever namespace runs it: an import, ``runpy``, or a reload. A class body declares them
global, so a namespace a metaclass prepares is never asked for them. The
names are reserved for pyct (`pyct.intercept`).

Positions follow the compiled code, not the source text. The call takes the
compare's whole position, which is where CPython puts the compare's own
instruction and the jump that tests it, even under a folded ``not``. The
name sits on the line where the left operand's first instruction does
(`positions.Parts.named`), so it adds no line: a plain name, since CPython moves
a method call's own instruction to its attribute's line. A container
display beside `in` is compiled as CPython compiles it there: a list
becomes a tuple, and a list or set of constants one constant at the
display's position. A set or dict display whose elements or keys are all
constants also hands over those constants, in the order written, each once,
as the display holds them.

The operators a plain number on the left may hand to a tracked value are
`operators`', and the calls of a conversion or of a method str has are
`calls`'. Each rule takes the node the walk meets, and a node no rule takes
stays as written.

Annotations are left alone: under ``from __future__ import annotations``
Python keeps one as its text, which the seed checks read.
"""

from __future__ import annotations

import ast

from pyct.intercept import calls, operators
from pyct.intercept.positions import Parts, constants, statement_start

# the name each operator calls
_NAMES: dict[type[ast.cmpop], str] = {
    ast.Is: "__pyct_is__",
    ast.IsNot: "__pyct_is_not__",
    ast.In: "__pyct_in__",
    ast.NotIn: "__pyct_not_in__",
}
# the function of pyct.core.substitutes each name any rule calls is bound to
BOUND: dict[str, str] = {
    "__pyct_is__": "is_",
    "__pyct_is_not__": "is_not",
    "__pyct_in__": "in_",
    "__pyct_not_in__": "not_in",
    **operators.BOUND,
    **calls.BOUND,
}
_NEGATED: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

# the module the bound names come from
_SUBSTITUTES = "pyct.core.substitutes"

# the largest display whose constants are handed over; a larger one is Python's own lookup
WRITTEN_MOST = 100

# the fields that hold an annotation, by the node that holds them
_ANNOTATIONS: dict[type[ast.AST], str] = {
    ast.arg: "annotation",
    ast.AnnAssign: "annotation",
    ast.FunctionDef: "returns",
    ast.AsyncFunctionDef: "returns",
}


def substitute(tree: ast.Module) -> ast.Module:
    """Replace every operation a rule takes in the tree, in place, and return the tree.

    The walk keeps its own stack rather than recursing, so a deeply nested
    expression, such as a long chain of `+`, needs no deeper Python stack
    than a shallow one. Which parts may fold is worked out once, before the
    walk. A tree with a substitution binds the names it calls, and only
    those, so a module's import costs one name per kind of operation it
    substitutes.
    """
    parts = Parts(tree)
    pending: list[ast.AST] = [tree]
    classes: list[ast.ClassDef] = []
    called: set[str] = set()
    while pending:
        node = pending.pop()
        if isinstance(node, ast.ClassDef):
            classes.append(node)
        skipped = _ANNOTATIONS.get(type(node))
        for field, value in ast.iter_fields(node):
            if field == skipped:
                continue
            if isinstance(value, list):
                value[:] = [_visited(item, pending, parts) for item in value]
            elif isinstance(value, ast.AST):
                setattr(node, field, _visited(value, pending, parts))
        if isinstance(node, ast.Name) and node.id in BOUND:
            called.add(node.id)
    if called:
        _bind(tree, classes, [name for name in BOUND if name in called])
    return tree


def _visited(node: object, pending: list[ast.AST], parts: Parts) -> object:
    """The node, or the call that replaces it, queued so the walk goes on inside it."""
    if not isinstance(node, ast.AST):
        return node
    replacement = (
        _compared(node, parts) or operators.replaced(node, parts) or calls.replaced(node, parts)
    )
    replacement = replacement or node
    pending.append(replacement)
    return replacement


def _compared(node: ast.AST, parts: Parts) -> ast.Call | None:
    """The call that replaces a compare of the three shapes, or None for any other node."""
    folded = _folded(node)
    if folded is None:
        return None
    compare, operator = folded
    left, right = compare.left, compare.comparators[0]
    if operator in (ast.Is, ast.IsNot) and not (_is_bool(left) or _is_bool(right)):
        return None
    function = parts.named(_NAMES[operator], left)
    arguments = [left, right] if operator in (ast.Is, ast.IsNot) else [left, *_container(right)]
    return ast.copy_location(ast.Call(func=function, args=arguments, keywords=[]), compare)


def _folded(node: ast.AST) -> tuple[ast.Compare, type[ast.cmpop]] | None:
    """The compare under any number of `not`, and its operator with each `not` folded in.

    Only a compare with one `is`, `is not`, `in` or `not in` folds, as in
    CPython; anything else is None.
    """
    negated = False
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node, negated = node.operand, not negated
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return None
    operator = type(node.ops[0])
    if operator not in _NEGATED:
        return None
    return node, _NEGATED[operator] if negated else operator


def _is_bool(node: ast.expr) -> bool:
    """Whether the node is the constant True or False itself, not a value equal to one."""
    return isinstance(node, ast.Constant) and (node.value is True or node.value is False)


def _container(display: ast.expr) -> list[ast.expr]:
    """The container as CPython compiles it beside `in`, then any constants it was written with."""
    if isinstance(display, ast.List) and not _starred(display.elts):
        folded = constants(display.elts, display)
        if folded is None:
            return [ast.copy_location(ast.Tuple(elts=display.elts, ctx=ast.Load()), display)]
        return [_constant(folded, display)]
    if isinstance(display, ast.Set):
        folded = constants(display.elts, display)
        if folded is None:
            return [display]
        return [_constant(frozenset(folded), display), *_written(folded, display)]
    if isinstance(display, ast.Dict):
        # a key of None is a `**` unpacking, whose keys the display does not write
        keys = [key for key in display.keys if key is not None]
        if len(keys) == len(display.keys):
            return [display, *_written(constants(keys, display), display)]
    return [display]


def _starred(elements: list[ast.expr]) -> bool:
    return any(isinstance(element, ast.Starred) for element in elements)


def _written(folded: tuple[object, ...] | None, display: ast.expr) -> list[ast.expr]:
    """The constants a set or dict display holds, in the order written, when there are few enough.

    An element equal to an earlier one is dropped, as the display drops it:
    `{1, True, 1}` holds the 1 alone.
    """
    if folded is None:
        return []
    held: set[object] = set()
    kept = [element for element in folded if not (element in held or held.add(element))]
    return [] if len(kept) > WRITTEN_MOST else [_constant(tuple(kept), display)]


def _constant(value: tuple[object, ...] | frozenset[object], display: ast.expr) -> ast.expr:
    """A constant at the display's position, where CPython puts the one it folds a display to."""
    # a Constant holds a tuple or a frozenset of constants too, which typeshed leaves out
    return ast.copy_location(ast.Constant(value=value), display)  # pyrefly: ignore[bad-argument-type]


def _bind(tree: ast.Module, classes: list[ast.ClassDef], names: list[str]) -> None:
    """Import the names into the module, and declare them global in every class body.

    The import goes before the module's first statement that runs code, at
    that code's first line and column, which it shares, so it adds no line.
    A module of a docstring and ``__future__`` imports alone runs nothing to
    substitute. A ``global`` statement compiles to no instruction at all.
    """
    body = tree.body
    start = _after_preamble(body, module=True)
    for index in range(start, len(body)):
        found = statement_start(body[:start], body[index])
        if found is not None:
            body.insert(index, _imported(names, *found))
            break
    for owner in classes:
        place = _after_preamble(owner.body, module=False)
        where = owner.body[min(place, len(owner.body) - 1)]
        declared = ast.Global(names=names)
        owner.body.insert(place, _at(declared, where.lineno, where.col_offset))


def _imported(names: list[str], line: int, column: int) -> ast.ImportFrom:
    """``from pyct.core.substitutes import in_ as __pyct_in__, ...``, placed at one spot."""
    aliases = [_at(ast.alias(name=BOUND[name], asname=name), line, column) for name in names]
    return _at(ast.ImportFrom(module=_SUBSTITUTES, names=aliases, level=0), line, column)


def _after_preamble(body: list[ast.stmt], *, module: bool) -> int:
    """Where the first statement after a docstring, and a module's ``__future__`` imports, is."""
    index = 0
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        index = 1 if isinstance(body[0].value.value, str) else 0
    while module and index < len(body) and _future(body[index]):
        index += 1
    return index


def _future(statement: ast.stmt) -> bool:
    return isinstance(statement, ast.ImportFrom) and statement.module == "__future__"


def _at[Placed: ast.stmt | ast.alias](node: Placed, line: int, column: int) -> Placed:
    """The node placed at one line and column, taking no room of its own."""
    node.lineno = node.end_lineno = line
    node.col_offset = node.end_col_offset = column
    return node
