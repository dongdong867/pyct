"""The compares pyct substitutes where the target writes them.

Three shapes, each a compare with one operator:

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
statement that runs, after its docstring and its ``__future__`` imports and
on that statement's own line, so the code has them in whatever namespace
runs it: an import, ``runpy``, or a reload. A class body declares them
global, so a namespace a metaclass prepares is never asked for them. The
names are reserved for pyct (`pyct.intercept`).

Positions follow the compiled code, not the source text. The call takes the
compare's whole position, which is where CPython puts the compare's own
instruction and the jump that tests it, even under a folded ``not``. The
name sits on the line where the left operand's first instruction does
(`positions.first`), so it adds no line: a plain name, since CPython moves
a method call's own instruction to its attribute's line. A container
display beside `in` is compiled as CPython compiles it there: a list
becomes a tuple, and a list or set of constants one constant at the
display's position. A set or dict display whose elements or keys are all
constants also hands over those constants, in the order written, each once,
as the display holds them.

Annotations are left alone: under ``from __future__ import annotations``
Python keeps one as its text, which the seed checks read.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import constants, first, statement_start

# the name each operator calls
_NAMES: dict[type[ast.cmpop], str] = {
    ast.Is: "__pyct_is__",
    ast.IsNot: "__pyct_is_not__",
    ast.In: "__pyct_in__",
    ast.NotIn: "__pyct_not_in__",
}
# the function of pyct.core.substitutes each of those names is bound to
BOUND: dict[str, str] = {
    "__pyct_is__": "is_",
    "__pyct_is_not__": "is_not",
    "__pyct_in__": "in_",
    "__pyct_not_in__": "not_in",
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
    """Replace every compare of the three shapes in the tree, in place, and return the tree.

    The walk keeps its own stack rather than recursing, so a deeply nested
    expression, such as a long chain of `+`, needs no deeper Python stack
    than a shallow one. A tree with a substitution binds the names it calls.
    """
    pending: list[ast.AST] = [tree]
    classes: list[ast.ClassDef] = []
    substituted = False
    while pending:
        node = pending.pop()
        if isinstance(node, ast.ClassDef):
            classes.append(node)
        skipped = _ANNOTATIONS.get(type(node))
        for field, value in ast.iter_fields(node):
            if field == skipped:
                continue
            if isinstance(value, list):
                value[:] = [_visited(item, pending) for item in value]
            elif isinstance(value, ast.AST):
                setattr(node, field, _visited(value, pending))
        substituted = substituted or _calls_a_substitute(node)
    if substituted:
        _bind(tree, classes)
    return tree


def _visited(node: object, pending: list[ast.AST]) -> object:
    """The node, or the call that replaces it, queued so the walk goes on inside it."""
    if not isinstance(node, ast.AST):
        return node
    replacement = _replacement(node) or node
    pending.append(replacement)
    return replacement


def _calls_a_substitute(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id in BOUND


def _replacement(node: ast.AST) -> ast.Call | None:
    """The call that replaces a compare of the three shapes, or None for any other node."""
    folded = _folded(node)
    if folded is None:
        return None
    compare, operator = folded
    left, right = compare.left, compare.comparators[0]
    if operator in (ast.Is, ast.IsNot) and not (_is_bool(left) or _is_bool(right)):
        return None
    function = _function(_NAMES[operator], left)
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


def _function(name: str, left: ast.expr) -> ast.Name:
    """The function's name, placed where the left operand's first instruction is."""
    start = first(left)
    return ast.Name(
        id=name,
        ctx=ast.Load(),
        lineno=start.lineno,
        col_offset=start.col_offset,
        end_lineno=start.lineno,
        end_col_offset=start.col_offset,
    )


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


def _bind(tree: ast.Module, classes: list[ast.ClassDef]) -> None:
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
            body.insert(index, _imported(*found))
            break
    for owner in classes:
        place = _after_preamble(owner.body, module=False)
        where = owner.body[min(place, len(owner.body) - 1)]
        declared = ast.Global(names=list(BOUND))
        owner.body.insert(place, _at(declared, where.lineno, where.col_offset))


def _imported(line: int, column: int) -> ast.ImportFrom:
    """``from pyct.core.substitutes import in_ as __pyct_in__, ...``, placed at one spot."""
    names = [
        _at(ast.alias(name=function, asname=name), line, column) for name, function in BOUND.items()
    ]
    return _at(ast.ImportFrom(module=_SUBSTITUTES, names=names, level=0), line, column)


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
