"""Where CPython puts an expression's first instruction, and what it folds to a constant.

A substituted call must add no line to the module's line table, so the name
it calls sits on the line of the left operand's first instruction. That is
the part of the operand evaluated first: the left of an operator, the object
of an attribute or a subscript, the test of a conditional. A part CPython
folds to one constant, or builds before its first element, is its own first.
These rules follow CPython 3.12's code generator (`CHECKED_ON`); the
lines-up check in the suite holds them to it.
"""

from __future__ import annotations

import ast
import dis
import warnings

from pyct.intercept.constants import Constants, literal_names

# the Python releases whose code generator these rules were checked against, by the suite's
# lines-up check. Substitution acts on these alone
CHECKED_ON: frozenset[tuple[int, int]] = frozenset({(3, 12)})

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

# what CPython may fold to a constant: constants, and operators, tuples and subscripts of them
_FOLDABLE = (ast.Constant, ast.BinOp, ast.UnaryOp, ast.Tuple, ast.Subscript)


def first(node: ast.expr) -> ast.expr:
    """The part of an expression whose line CPython gives the expression's first instruction.

    Every part of an expression on one line is on that line, so the walk
    goes down only while the part spans lines. Which parts may fold is
    worked out once for the whole expression, so a long chain costs one
    pass.
    """
    return Parts(node).first(node)


class Parts:
    """What a walk over one tree works out once: which parts may fold, and where each part's
    first instruction is.

    A walk that substitutes every `+` of a long chain asks for the first
    instruction of each link, and each link's is the one below it, so the
    answer is kept for every part the search passed through, and the chain
    costs one pass. Each part is kept with its answer, so no part the tree
    let go of can lend its id to another.
    """

    def __init__(self, root: ast.AST) -> None:
        self.foldable = _foldable(root)
        self._firsts: dict[int, tuple[ast.expr, ast.expr]] = {}
        # worked out before the walk changes the tree, from the module as written
        self.constants: Constants = literal_names(root)

    def first(self, node: ast.expr) -> ast.expr:
        """The part of an expression whose line CPython gives the expression's first instruction."""
        passed: list[ast.expr] = []
        while node.lineno != node.end_lineno:
            if id(node) in self._firsts:
                node = self._firsts[id(node)][1]
                break
            passed.append(node)
            if isinstance(node, ast.Call) and not _method_call(node):
                # CPython pushes the call's NULL at the callee's own position, before the callee
                node = node.func
                break
            part = _evaluated_first(node, self.foldable)
            if part is None:
                break
            node = part
        for each in passed:
            self._firsts[id(each)] = (each, node)
        return node

    def named(self, name: str, operand: ast.expr) -> ast.Name:
        """A name to call, placed where the operand's first instruction is, so it adds no line.

        A plain name, since CPython moves a method call's own instruction to
        its attribute's line.
        """
        start = self.first(operand)
        return ast.Name(
            id=name,
            ctx=ast.Load(),
            lineno=start.lineno,
            col_offset=start.col_offset,
            end_lineno=start.lineno,
            end_col_offset=start.col_offset,
        )

    def folded(self, node: ast.expr) -> tuple[object] | None:
        """The one constant CPython folds the expression to, in a tuple, or None if it does not."""
        if id(node) not in self.foldable:
            return None
        held = constants([node], node)
        return None if held is None else (held[0],)


def constants(elements: list[ast.expr], display: ast.expr) -> tuple[object, ...] | None:
    """The elements as the one tuple constant CPython folds them to, or None when it does not.

    The running CPython answers: the elements are compiled alone, as a tuple,
    and are constants when its code loads one constant and returns it.
    Asking the compiler keeps the rule for what it folds its own. Its
    warnings are the module's to give, once, when the module itself
    compiles.
    """
    if not all(id(element) in _foldable(element) for element in elements):
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


def _evaluated_first(node: ast.expr, foldable: set[int]) -> ast.expr | None:
    """The part of the node CPython evaluates before the rest of it, or None when it has none."""
    if isinstance(node, ast.Call):
        method = node.func
        return method.value if isinstance(method, ast.Attribute) else None
    if isinstance(node, ast.BinOp | ast.UnaryOp):
        # a part CPython folds to a constant is loaded at its own position
        if id(node) in foldable and constants([node], node) is not None:
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
    """Whether CPython compiles the call as a method call, evaluating its object first."""
    unpacked = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    )
    count = len(call.args) + len(call.keywords) + (1 if call.keywords else 0)
    return isinstance(call.func, ast.Attribute) and not unpacked and count < _STACK_GUIDELINE


def _first_entry(display: ast.Dict) -> ast.expr | None:
    """A dict display's first key, or its first value when CPython loads its keys as one constant.

    CPython builds the entries before the first `**` in one step, of at
    most 17; a step of 16 or more, or a display that opens with `**` or
    holds nothing, starts by building the dict.
    """
    keys: list[ast.expr] = []
    for key in display.keys[: _STACK_GUIDELINE // 2 + 2]:
        if key is None:
            break
        keys.append(key)
    if not keys or 2 * len(keys) > _STACK_GUIDELINE:
        return None
    if len(keys) > 1 and constants(keys, display) is not None:
        return display.values[0]
    return keys[0]


def _first_element(display: ast.Tuple | ast.List | ast.Set) -> ast.expr | None:
    """A display's first element, when CPython evaluates it before building the display."""
    elements = display.elts
    if not elements or len(elements) > _STACK_GUIDELINE or isinstance(elements[0], ast.Starred):
        return None
    folds = isinstance(display, ast.Tuple) or len(elements) > 2
    if folds and constants(elements, display) is not None:
        return None
    return elements[0]


def _foldable(root: ast.AST) -> set[int]:
    """The ids of the expressions under the root CPython may fold, each worked out once.

    A part may fold when it is a constant, or an operator, tuple or
    subscript whose every part may. The walk keeps its own stack, and goes
    through statements to the expressions they hold, so one pass serves a
    whole module.
    """
    order: list[ast.AST] = []
    pending: list[ast.AST] = [root]
    while pending:
        part = pending.pop()
        order.append(part)
        pending.extend(ast.iter_child_nodes(part))
    foldable: set[int] = set()
    for part in reversed(order):
        debug = isinstance(part, ast.Name) and part.id == "__debug__"
        if debug or (
            isinstance(part, _FOLDABLE) and all(id(each) in foldable for each in _parts(part))
        ):
            foldable.add(id(part))
    return foldable


def _parts(node: ast.expr) -> list[ast.expr]:
    return [child for child in ast.iter_child_nodes(node) if isinstance(child, ast.expr)]


def statement_start(preamble: list[ast.stmt], statement: ast.stmt) -> tuple[int, int] | None:
    """The line and column of the statement's first instruction, or None when it has none.

    The running CPython answers: the statement is compiled after the
    module's docstring and ``__future__`` imports, as it runs in the module,
    and its first positioned instruction is read. A decorator, a value
    spread over lines, or a parenthesized test puts it past the statement's
    own start; a ``global`` statement has none.
    """
    module = ast.Module(body=[*preamble, statement], type_ignores=[])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            code = compile(module, "<pyct probe>", "exec", dont_inherit=True)
    except SyntaxError:
        return None
    lowest = min(part.lineno for part in ast.walk(statement) if hasattr(part, "lineno"))
    for step in dis.get_instructions(code):
        line = step.positions.lineno if step.positions else None
        if step.opname != "RESUME" and line is not None and line >= lowest:
            column = step.positions.col_offset if step.positions else None
            return line, column or 0
    return None
