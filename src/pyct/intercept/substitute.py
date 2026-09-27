"""The compares pyct substitutes where the target writes them.

Three shapes, each a compare with one operator:

- ``a is True``, ``a is not False``, ``True is a``, ``a is b``: `is` or
  `is not` with no constant on either side but True or False, so ``a is
  None`` stays Python's own;
- ``a in b`` and ``a not in b``;
- ``not`` over one of those, folded into the other operator as CPython's
  optimizer folds it, so ``not (a in b)`` is ``a not in b``.

Each becomes a call of a function of `pyct.core.substitutes` through a
dunder name, ``__pyct_in__(a, b)`` say. The operands are the compare's own
nodes, moved into the call and never copied, so each is evaluated once and
in Python's order: the left, then the right, then the test.

A chained compare keeps its own shape, because CPython holds each operand
on its stack for the next link. An `in` or `not in` link searches its
container through ``__pyct_searched__(b)``, and an `is` or `is not` link
with True or False on its right becomes an `in` or `not in` on
``__pyct_identity__(True)``, and one with True or False on its left an
`in` on ``__pyct_identity__`` of its right operand: both are Python's own
`in`, which asks the container, so the link is answered by pyct at the
chain's own position. The next link meets what the call made as its left
operand, so an `is` link there becomes an `in` on ``__pyct_identity__``
whatever its right, and a compare runs on the operand the call holds
(interception-chain-links-searched-through-a-container).

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
(`positions.first`), so it adds no line: a plain name, since CPython moves
a method call's own instruction to its attribute's line. A container
display beside `in` is compiled as CPython compiles it there: a list
becomes a tuple, and a list or set of constants one constant at the
display's position. A set or dict display whose elements or keys are all
constants also hands over those constants, in the order written, each once,
as the display holds them, when there are at most `SEARCHED_MOST`: a larger
display is searched as any large set is.

Annotations are left alone: under ``from __future__ import annotations``
Python keeps one as its text, which the seed checks read.
"""

from __future__ import annotations

import ast

from pyct.core.hashed import SEARCHED_MOST
from pyct.intercept.positions import constants, first, statement_start

# the name each operator calls
_NAMES: dict[type[ast.cmpop], str] = {
    ast.Is: "__pyct_is__",
    ast.IsNot: "__pyct_is_not__",
    ast.In: "__pyct_in__",
    ast.NotIn: "__pyct_not_in__",
}
# the name a chain's `in` link searches through, and the one an `is` link's constant becomes
_SEARCHED = "__pyct_searched__"
_IDENTITY = "__pyct_identity__"
# the member of pyct.core.substitutes each name is bound to
BOUND: dict[str, str] = {
    "__pyct_is__": "is_",
    "__pyct_is_not__": "is_not",
    "__pyct_in__": "in_",
    "__pyct_not_in__": "not_in",
    _SEARCHED: "Searched",
    _IDENTITY: "Identity",
}
# the operator an `is` link becomes on pyct's identity
_AS_IN: dict[type[ast.cmpop], type[ast.cmpop]] = {ast.Is: ast.In, ast.IsNot: ast.NotIn}
_NEGATED: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}

# the module the bound names come from
_SUBSTITUTES = "pyct.core.substitutes"

# the fields that hold an annotation, by the node that holds them
_ANNOTATIONS: dict[type[ast.AST], str] = {
    ast.arg: "annotation",
    ast.AnnAssign: "annotation",
    ast.FunctionDef: "returns",
    ast.AsyncFunctionDef: "returns",
}


def substitute(tree: ast.Module) -> ast.Module:
    """Replace every compare of the three shapes in the tree, and each `in` or `is` link of a
    chained compare, in place, and return the tree.

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


def _replacement(node: ast.AST) -> ast.expr | None:
    """The call that replaces a compare of the three shapes, the chain that replaces a chained
    compare with a link to search, or None for any other node."""
    if isinstance(node, ast.Compare) and len(node.ops) > 1:
        return _chain(node)
    folded = _folded(node)
    if folded is None:
        return None
    compare, operator = folded
    left, right = compare.left, compare.comparators[0]
    if operator in (ast.Is, ast.IsNot) and (_other_constant(left) or _other_constant(right)):
        return None
    function = _function(_NAMES[operator], left)
    arguments = [left, right] if operator in (ast.Is, ast.IsNot) else [left, *_container(right)]
    return ast.copy_location(ast.Call(func=function, args=arguments, keywords=[]), compare)


def _chain(compare: ast.Compare) -> ast.Compare | None:
    """The chain with each link to search handed to pyct, or None when it has none."""
    ops, comparators = list(compare.ops), list(compare.comparators)
    lefts = [compare.left, *compare.comparators[:-1]]
    held = False
    for index, (operator, right) in enumerate(zip(compare.ops, compare.comparators, strict=True)):
        # an `is` link is pyct's after a link pyct took, whose call's operand the chain hands on
        # as its left, and wherever neither side is a constant but True or False
        ours = held or not (_other_constant(lefts[index]) or _other_constant(right))
        link = (
            None
            if _before_python_s_identity(compare, index)
            else _link(operator, right, last=index == len(ops) - 1, identity=ours)
        )
        if link is not None:
            ops[index], comparators[index] = link
        held = link is not None
    if comparators == compare.comparators:
        return None
    chain = ast.Compare(left=compare.left, ops=ops, comparators=comparators)
    return ast.copy_location(chain, compare)


def _before_python_s_identity(compare: ast.Compare, index: int) -> bool:
    """Whether the link after this one is an `is` against a constant other than True or False.

    Python answers that link itself, on the operand this link hands on, and
    CPython tests it with a jump of its own, `POP_JUMP_IF_NONE` say, which a
    call of pyct's in its place would change. So this link is Python's own
    too.
    """
    following = index + 1
    if following >= len(compare.ops):
        return False
    is_link = isinstance(compare.ops[following], ast.Is | ast.IsNot)
    return is_link and _other_constant(compare.comparators[following])


def _link(
    operator: ast.cmpop, right: ast.expr, *, last: bool, identity: bool
) -> tuple[ast.cmpop, ast.Call] | None:
    """One link's operator and the container it searches, or None for a link left to Python.

    ``identity`` says an `is` link is pyct's: its left is a call's operand,
    which the link before handed on, or neither side is a constant but True
    or False. Only the last link's container is compiled as CPython compiles it
    beside `in`, since CPython folds the display of that link alone.
    """
    if isinstance(operator, ast.In | ast.NotIn):
        return operator, _called(_SEARCHED, _container(right, folded=last), right)
    if isinstance(operator, ast.Is | ast.IsNot) and identity:
        return _AS_IN[type(operator)](), _called(_IDENTITY, [right], right)
    return None


def _called(name: str, arguments: list[ast.expr], operand: ast.expr) -> ast.Call:
    """A call of the name on the arguments, where the operand it stands for was.

    The name sits where the first argument's first instruction does, as the
    operand's first instruction was: a display CPython folds to a constant
    has its own.
    """
    call = ast.Call(func=_function(name, arguments[0]), args=arguments, keywords=[])
    return ast.copy_location(call, operand)


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


def _other_constant(node: ast.expr) -> bool:
    """Whether the node is a constant other than True and False, as `None` is: Python's own
    identity answers an `is` against it."""
    return isinstance(node, ast.Constant) and not _is_bool(node)


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


def _container(display: ast.expr, *, folded: bool = True) -> list[ast.expr]:
    """The container as CPython compiles it beside `in`, then any constants it was written with.

    A display CPython does not fold stays as written, and a set still hands
    over its constants.
    """
    if folded and isinstance(display, ast.List) and not _starred(display.elts):
        elements = constants(display.elts, display)
        if elements is None:
            return [ast.copy_location(ast.Tuple(elts=display.elts, ctx=ast.Load()), display)]
        return [_constant(elements, display)]
    if isinstance(display, ast.Set):
        elements = constants(display.elts, display)
        if elements is None:
            return [display]
        held = _constant(frozenset(elements), display) if folded else display
        return [held, *_written(elements, display)]
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
    return [] if len(kept) > SEARCHED_MOST else [_constant(tuple(kept), display)]


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
