"""The compares pyct substitutes where the target writes them.

Three shapes, each a compare with one operator:

- ``a is True``, ``a is not False``, ``True is a``: `is` or `is not` with
  the constant True or False on one side;
- ``a in b`` and ``a not in b``;
- ``not`` over one of those, folded into the other operator as CPython's
  optimizer folds it, so ``not (a in b)`` is ``a not in b``.

Each becomes a call of a function of `pyct.core.substitutes`, through the
name the loader binds it to in the module, ``__pyct_in__(a, b)`` say. The
operands are the compare's own nodes, moved into the call and never copied,
so each is evaluated once and in Python's order: the left, then the right,
then the test.

Positions follow the compiled code, not the source text. The call takes the
compare's whole position, which is where CPython puts the compare's own
instruction and the jump that tests it, even under a folded ``not``. The
name sits on the line where the left operand's first instruction does, so
it adds no line: a plain name, since CPython moves a method call's own
instruction to its attribute's line. A container display beside `in` is
compiled as CPython compiles it there: a list becomes a tuple, and a list
or set of constants one constant at the display's position, so a display
written over several lines adds no line either. A set or dict display whose
elements or keys are all constants also hands over those constants, in the
order written, as a tuple.

Annotations are left alone: under ``from __future__ import annotations``
Python keeps one as its text, which the seed checks read.
"""

from __future__ import annotations

import ast
import dis
import warnings

# the name each operator calls, which a substituted module holds before its code runs
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

# the largest display whose constants are handed over; a larger one is Python's own lookup
WRITTEN_MOST = 100

# CPython's STACK_USE_GUIDELINE: a call or a display with more parts than this is built in steps
_STACK_GUIDELINE = 30

# the field of each node CPython evaluates first, where it is always the same field
_FIRST_FIELDS: dict[type[ast.expr], str] = {
    ast.Attribute: "value",
    ast.Subscript: "value",
    ast.NamedExpr: "value",
    ast.Await: "value",
    ast.Yield: "value",
    ast.YieldFrom: "value",
    ast.FormattedValue: "value",
    ast.Compare: "left",
    ast.IfExp: "test",
}

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
    than a shallow one.
    """
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        skipped = _ANNOTATIONS.get(type(node))
        for field, value in ast.iter_fields(node):
            if field == skipped:
                continue
            if isinstance(value, list):
                value[:] = [_visited(item, pending) for item in value]
            elif isinstance(value, ast.AST):
                setattr(node, field, _visited(value, pending))
    return tree


def _visited(node: object, pending: list[ast.AST]) -> object:
    """The node, or the call that replaces it, queued so the walk goes on inside it."""
    if not isinstance(node, ast.AST):
        return node
    replacement = _replacement(node) or node
    pending.append(replacement)
    return replacement


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
    first = _first(left)
    return ast.Name(
        id=name,
        ctx=ast.Load(),
        lineno=first.lineno,
        col_offset=first.col_offset,
        end_lineno=first.lineno,
        end_col_offset=first.col_offset,
    )


def _first(node: ast.expr) -> ast.expr:
    """The part of an expression whose position CPython gives the expression's first instruction.

    It is the part evaluated first: the left of an operator, the object of
    an attribute, a call or a subscript, the test of a conditional. Every
    part of an expression on one line is on that line, so the walk goes
    down only while the part spans lines. A part CPython folds to one
    constant, or builds before its first element, is its own first.
    """
    while node.lineno != node.end_lineno:
        part = _evaluated_first(node)
        if part is None:
            break
        node = part
    return node


def _evaluated_first(node: ast.expr) -> ast.expr | None:
    """The part of the node CPython evaluates before the rest of it, or None when it has none."""
    if isinstance(node, ast.Call):
        method = node.func
        return method.value if isinstance(method, ast.Attribute) and _method_call(node) else None
    if isinstance(node, ast.BinOp | ast.UnaryOp):
        # a part CPython folds to a constant is loaded at its own position
        if _constants([node], node) is not None:
            return None
        return node.left if isinstance(node, ast.BinOp) else node.operand
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return _first_element(node)
    if isinstance(node, ast.Dict):
        return _first_entry(node)
    if isinstance(node, ast.ListComp | ast.SetComp | ast.DictComp):
        # CPython runs the comprehension inline, from its first iterable
        return node.generators[0].iter
    if isinstance(node, ast.BoolOp | ast.JoinedStr):
        return node.values[0] if node.values else None
    field = _FIRST_FIELDS.get(type(node))
    return None if field is None else getattr(node, field)


def _method_call(call: ast.Call) -> bool:
    """Whether CPython compiles the call as a method call, evaluating its object first.

    Otherwise its first instruction sits at the called expression's own
    position.
    """
    unpacked = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    )
    count = len(call.args) + len(call.keywords) + (1 if call.keywords else 0)
    return not unpacked and count < _STACK_GUIDELINE


def _first_entry(display: ast.Dict) -> ast.expr | None:
    """A dict display's first key, or its first value when CPython loads its keys as one constant.

    A display that opens with an unpacking, or holds nothing, starts by
    building the dict.
    """
    keys = display.keys
    if not keys or keys[0] is None:
        return None
    constant_keys = len(keys) > 1 and None not in keys
    if constant_keys and _constants([key for key in keys if key is not None], display):
        return None if 2 * len(keys) > _STACK_GUIDELINE else display.values[0]
    return keys[0]


def _first_element(display: ast.Tuple | ast.List | ast.Set) -> ast.expr | None:
    """A display's first element, when CPython evaluates it before building the display."""
    elements = display.elts
    if not elements or len(elements) > _STACK_GUIDELINE or isinstance(elements[0], ast.Starred):
        return None
    folds = isinstance(display, ast.Tuple) or len(elements) > 2
    if folds and _constants(elements, display) is not None:
        return None
    return elements[0]


def _container(display: ast.expr) -> list[ast.expr]:
    """The container as CPython compiles it beside `in`, then any constants it was written with."""
    if isinstance(display, ast.List) and not _starred(display.elts):
        folded = _constants(display.elts, display)
        if folded is None:
            return [ast.copy_location(ast.Tuple(elts=display.elts, ctx=ast.Load()), display)]
        return [_constant(folded, display)]
    if isinstance(display, ast.Set):
        folded = _constants(display.elts, display)
        if folded is None:
            return [display]
        return [_constant(frozenset(folded), display), *_written(folded, display)]
    if isinstance(display, ast.Dict):
        # a key of None is a `**` unpacking, whose keys the display does not write
        keys = [key for key in display.keys if key is not None]
        if len(keys) == len(display.keys):
            return [display, *_written(_constants(keys, display), display)]
    return [display]


def _starred(elements: list[ast.expr]) -> bool:
    return any(isinstance(element, ast.Starred) for element in elements)


def _written(folded: tuple[object, ...] | None, display: ast.expr) -> list[ast.expr]:
    """The constants a set or dict display was written with, when there are few enough."""
    if folded is None or len(folded) > WRITTEN_MOST:
        return []
    return [_constant(folded, display)]


def _constant(value: tuple[object, ...] | frozenset[object], display: ast.expr) -> ast.expr:
    """A constant at the display's position, where CPython puts the one it folds a display to."""
    # a Constant holds a tuple or a frozenset of constants too, which typeshed leaves out
    return ast.copy_location(ast.Constant(value=value), display)  # pyrefly: ignore[bad-argument-type]


def _constants(elements: list[ast.expr], display: ast.expr) -> tuple[object, ...] | None:
    """The elements as the one tuple constant CPython folds them to, or None when it does not.

    The running CPython answers: the elements are compiled alone, as a tuple,
    and are constants when its code loads one constant and returns it.
    Asking the compiler keeps the rule for what it folds its own, whatever
    the release. Its warnings are the module's to give, once, when the
    module itself compiles.
    """
    if not all(_may_fold(element) for element in elements):
        return None
    probe = ast.Expression(
        body=ast.copy_location(ast.Tuple(elts=elements, ctx=ast.Load()), display)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        code = compile(probe, "<pyct probe>", "eval", dont_inherit=True)
    steps = [step for step in dis.get_instructions(code) if step.opname not in ("RESUME", "NOP")]
    names = [step.opname for step in steps]
    if names == ["RETURN_CONST"] or names == ["LOAD_CONST", "RETURN_VALUE"]:
        value = steps[0].argval
        return value if isinstance(value, tuple) else None
    return None


# what CPython may fold to a constant: constants, and operators, tuples and subscripts of them
_FOLDABLE = (ast.Constant, ast.BinOp, ast.UnaryOp, ast.Tuple, ast.Subscript)


def _may_fold(node: ast.expr) -> bool:
    """Whether every part of the expression is one CPython may fold, worth asking the compiler.

    The last part is looked at first, so a long chain of operators on
    names answers at its first operator.
    """
    pending: list[ast.AST] = [node]
    while pending:
        part = pending.pop()
        if isinstance(part, ast.Name) and part.id == "__debug__":
            continue
        if not isinstance(part, _FOLDABLE):
            return False
        pending.extend(child for child in ast.iter_child_nodes(part) if isinstance(child, ast.expr))
    return True
