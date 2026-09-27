"""The operations pyct substitutes where the target writes them.

The compares with `is` and `in` are here, in three shapes, each a compare
with one operator:

- ``a is True``, ``a is not False``, ``True is a``, ``flag is b``: `is` or
  `is not` with True or False on one side, or a name the module binds to
  bools alone (`constants`), and no other constant, so ``a is None`` and
  ``a is b`` stay Python's own;
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
the rule above takes becomes an `in` or `not in` on
``__pyct_identity__(b)``: both are Python's own `in`, which asks the
container, so the link is answered by pyct at the chain's own position.
The next link meets what the call made as its left operand, so an `is`
link there becomes an `in` on ``__pyct_identity__`` whatever its right,
and a compare runs on the operand the call holds
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
(`positions.Parts.named`), so it adds no line: a plain name, since CPython moves
a method call's own instruction to its attribute's line. A container
display beside `in` is compiled as CPython compiles it there: a list
becomes a tuple, and a list or set of constants one constant at the
display's position. A set or dict display whose elements or keys are all
constants also hands over those constants, in the order written, each once,
as the display holds them, when there are at most `SEARCHED_MOST`: a larger
display is searched as any large set is.

The operators a plain number on the left may hand to a tracked value are
`operators`', the calls of a conversion or of a method str has are
`calls`', and the `return` of a `__bool__` method is `bool_returns`', which
the walk hands each class it meets. Each rule takes the node the walk
meets, and a node no rule takes stays as written.

Annotations are left alone: under ``from __future__ import annotations``
Python keeps one as its text, which the seed checks read.
"""

from __future__ import annotations

import ast

from pyct.core.hashed import SEARCHED_MOST
from pyct.intercept import bool_returns, calls, operators
from pyct.intercept.positions import Parts, constants, statement_start

# the name each operator calls
_NAMES: dict[type[ast.cmpop], str] = {
    ast.Is: "__pyct_is__",
    ast.IsNot: "__pyct_is_not__",
    ast.In: "__pyct_in__",
    ast.NotIn: "__pyct_not_in__",
}
# the name a chain's `in` link searches through, and the one an `is` link's right side becomes
_SEARCHED = "__pyct_searched__"
_IDENTITY = "__pyct_identity__"
# the function of pyct.core.substitutes each name any rule calls is bound to
BOUND: dict[str, str] = {
    "__pyct_is__": "is_",
    "__pyct_is_not__": "is_not",
    "__pyct_in__": "in_",
    "__pyct_not_in__": "not_in",
    _SEARCHED: "Searched",
    _IDENTITY: "Identity",
    **operators.BOUND,
    **calls.BOUND,
    **bool_returns.BOUND,
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
            _met_class(node, classes, parts)
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


def _met_class(owner: ast.ClassDef, classes: list[ast.ClassDef], parts: Parts) -> None:
    """Keep a class the walk meets, whose body declares the bound names global, and hand over
    the value of each `return` of its `__bool__` method before the walk goes inside, so the walk
    meets each value in the call that holds it."""
    classes.append(owner)
    bool_returns.hand_over(owner, parts)


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


def _compared(node: ast.AST, parts: Parts) -> ast.expr | None:
    """The call that replaces a compare of the three shapes, the chain that replaces a chained
    compare with a link to search, or None for any other node."""
    if isinstance(node, ast.Compare) and len(node.ops) > 1:
        return _chain(node, parts)
    folded = _folded(node)
    if folded is None:
        return None
    compare, operator = folded
    left, right = compare.left, compare.comparators[0]
    if operator in (ast.Is, ast.IsNot) and not _pyct_s_identity(left, right, parts):
        return None
    function = parts.named(_NAMES[operator], left)
    arguments = [left, right] if operator in (ast.Is, ast.IsNot) else [left, *_container(right)]
    return ast.copy_location(ast.Call(func=function, args=arguments, keywords=[]), compare)


def _chain(compare: ast.Compare, parts: Parts) -> ast.Compare | None:
    """The chain with each link to search handed to pyct, or None when it has none."""
    ops, comparators = list(compare.ops), list(compare.comparators)
    lefts = [compare.left, *compare.comparators[:-1]]
    held = False
    for index, (operator, right) in enumerate(zip(compare.ops, compare.comparators, strict=True)):
        # an `is` link is pyct's after a link pyct took, whose call's operand the chain hands on
        # as its left, and where `_pyct_s_identity` says
        ours = held or _pyct_s_identity(lefts[index], right, parts)
        link = _link(operator, right, parts, last=index == len(ops) - 1, identity=ours)
        if link is not None:
            ops[index], comparators[index] = link
        held = link is not None
    if comparators == compare.comparators:
        return None
    chain = ast.Compare(left=compare.left, ops=ops, comparators=comparators)
    return ast.copy_location(chain, compare)


def _link(
    operator: ast.cmpop, right: ast.expr, parts: Parts, *, last: bool, identity: bool
) -> tuple[ast.cmpop, ast.Call] | None:
    """One link's operator and the container it searches, or None for a link left to Python.

    ``identity`` says an `is` link is pyct's: its left is a call's operand,
    which the link before handed on, or `_pyct_s_identity` takes it. Only
    the last link's container is compiled as CPython compiles it beside
    `in`, since CPython folds the display of that link alone. An `is` link
    pyct takes before an `is` against None turns the jump CPython fuses
    with that `is`, `POP_JUMP_IF_NONE` say, into a plain `POP_JUMP_IF_FALSE`
    on the same outcome, which the lines-up check allows.
    """
    if isinstance(operator, ast.In | ast.NotIn):
        return operator, _called(_SEARCHED, _container(right, folded=last), right, parts)
    if isinstance(operator, ast.Is | ast.IsNot) and identity:
        return _AS_IN[type(operator)](), _called(_IDENTITY, [right], right, parts)
    return None


def _called(name: str, arguments: list[ast.expr], operand: ast.expr, parts: Parts) -> ast.Call:
    """A call of the name on the arguments, where the operand it stands for was.

    The name sits where the first argument's first instruction does, as the
    operand's first instruction was: a display CPython folds to a constant
    has its own.
    """
    call = ast.Call(func=parts.named(name, arguments[0]), args=arguments, keywords=[])
    return ast.copy_location(call, operand)


def _pyct_s_identity(left: ast.expr, right: ast.expr, parts: Parts) -> bool:
    """Whether an `is` between the two is pyct's: True or False on a side, or a name the module
    binds to bools alone (`constants`), with no other constant on either side.

    Any other `is` is Python's own, so plain identity code runs as fast as
    written; two tracked bools that no such name holds answer by identity.
    """
    if _other_constant(left) or _other_constant(right):
        return False
    held = parts.constants.holds_a_bool
    return _is_bool(left) or _is_bool(right) or held(left) or held(right)


def _other_constant(node: ast.expr) -> bool:
    """Whether the node is a constant other than True and False, as `None` is: Python's own
    identity answers an `is` against it."""
    return isinstance(node, ast.Constant) and not _is_bool(node)


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
