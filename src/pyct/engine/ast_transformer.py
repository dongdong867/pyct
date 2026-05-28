"""AST transformer — rewrites target source so builtins route through concolic helpers.

Python's C-level fast paths for ``int()``, ``str()``, ``range()``, and
``x is y`` strip concolic wrappers before the engine ever sees the
branch. The canonical workaround, taken from upstream PyCT's
``libct/wrapper.py``, is to rewrite target source at load time so
these call sites dispatch through pure-Python helpers that preserve
symbolic tracking.

Scope of this module:

* ``ConcolicCallRewriter`` — rewrites ``int(x)``, ``str(x)``,
  ``range(...)`` Call nodes. Multi-arg ``int(x, base)`` and
  ``str(x, encoding)`` are left untouched — upstream's convention is
  to skip call shapes whose semantics we haven't modelled.
* ``ConcolicCompareRewriter`` — rewrites ``x is y`` Compare nodes with
  a single ``is`` operator and a single comparator. ``is not`` and
  chained comparisons are left alone.
* ``rewrite_target`` — applies both rewriters to a callable's source,
  compiles the transformed tree against the ORIGINAL source filename
  (preserving line numbers for ``sys.settrace``), and execs it in the
  target's own ``__globals__`` so module-level references still
  resolve. Returns the new callable.

Intentionally NOT ported from upstream:

* Constant wrapping (``ConcolicWrapperConstant``) — would touch every
  literal in the target, creating a large regression surface.
* Assignment wrapping (``ConcolicWrapperAssign``) — same reason.
* FunctionDef/ClassDef transformers — specific to upstream's class
  system, not applicable here.

The rewrite is local to one function, not module-wide. This means
closures over free variables don't survive (benchmark targets are all
top-level functions, so this is a non-issue in practice).
"""

from __future__ import annotations

import ast
import inspect
import logging
import textwrap
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyct.engine.state import ExplorationState

log = logging.getLogger("ct.engine.ast_transformer")

_INT_HELPER = "pyct.core.builtin_wrappers._int"
_STR_HELPER = "pyct.core.builtin_wrappers._str"
_IS_HELPER = "pyct.core.builtin_wrappers._is"
_RANGE_CLASS = "pyct.core.concolic_range.ConcolicRange"

# Empty-constructor calls Python treats as empty container literals for the
# purposes of ``x in <empty>`` (always False). Listed at module scope so the
# Compare rewriter can detect them as equivalent to an empty Set/Tuple/List/
# Dict literal node.
_EMPTY_CONSTRUCTOR_NAMES = frozenset({"set", "frozenset", "tuple", "list", "dict"})


class ConcolicCallRewriter(ast.NodeTransformer):
    """Rewrites ``int(x)``, ``str(x)``, ``range(...)``, ``map(int, x)`` Call nodes."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if not isinstance(node.func, ast.Name):
            return node
        name = node.func.id
        if name == "int" and len(node.args) == 1 and not node.keywords:
            return _build_helper_call(_INT_HELPER, node)
        if name == "str" and len(node.args) == 1 and not node.keywords:
            return _build_helper_call(_STR_HELPER, node)
        if name == "range":
            return _build_helper_call(_RANGE_CLASS, node)
        if name == "map" and _is_map_int(node):
            return _build_map_int_comprehension(node)
        return node


_MAP_INT_INDEX_VAR = "_pyct_map_int_i"


def _is_map_int(node: ast.Call) -> bool:
    """Return True for ``map(int, x)`` whose iterable is a bare Name.

    Restricting to Name iterables keeps the rewrite single-evaluation:
    the expanded form references the iterable twice (inside ``len`` and
    inside the subscript), and a Name is the only shape where reading
    it twice is observably identical to the original ``map`` call.
    """
    if len(node.args) != 2 or node.keywords:
        return False
    func, iterable = node.args
    if not isinstance(func, ast.Name) or func.id != "int":
        return False
    return isinstance(iterable, ast.Name)


def _build_map_int_comprehension(node: ast.Call) -> ast.AST:
    """Rewrite ``map(int, x)`` as ``[_int(x[_i]) for _i in _Range(len(x))]``.

    Expanding ``map`` lets each per-character ``int`` go through the
    ``_int`` helper at execution time, so symbolic tracking survives the
    ``map(int, x)`` surface syntax that otherwise hides the int wraps
    from the Call rewriter (``map`` looks up ``int`` once at call time
    and the rewrite never sees a ``Call(int, ...)`` node to transform).
    """
    iterable_name = node.args[1]
    assert isinstance(iterable_name, ast.Name)

    def _named(name_id: str, ctx: ast.expr_context) -> ast.Name:
        ref = ast.Name(id=name_id, ctx=ctx)
        ast.copy_location(ref, node)
        return ref

    subscript = ast.Subscript(
        value=_named(iterable_name.id, ast.Load()),
        slice=_named(_MAP_INT_INDEX_VAR, ast.Load()),
        ctx=ast.Load(),
    )
    ast.copy_location(subscript, node)
    int_call = _build_helper_call_from_args(_INT_HELPER, [subscript], node)

    len_call = ast.Call(
        func=ast.Name(id="len", ctx=ast.Load()),
        args=[_named(iterable_name.id, ast.Load())],
        keywords=[],
    )
    ast.copy_location(len_call, node)
    for child in ast.walk(len_call):
        ast.copy_location(child, node)
    range_call = _build_helper_call_from_args(_RANGE_CLASS, [len_call], node)

    comp = ast.ListComp(
        elt=int_call,
        generators=[
            ast.comprehension(
                target=_named(_MAP_INT_INDEX_VAR, ast.Store()),
                iter=range_call,
                ifs=[],
                is_async=0,
            )
        ],
    )
    ast.copy_location(comp, node)
    return comp


_IS_REWRITE_LITERALS = (None, True, False, Ellipsis)


class ConcolicCompareRewriter(ast.NodeTransformer):
    """Rewrites ``x is <literal>`` and ``x in <literal-container>`` Compares.

    Two rewrites live here, both gated on a single op and single comparator:

    * ``x is None`` / ``x is True`` / ``x is False`` / ``x is ...`` → routes
      through ``_is`` so the concolic wrapper unwrap-check matches the
      author's sentinel intent. Variable-RHS ``is`` checks are left
      untouched because the concolic layer can't preserve Python's
      object-identity semantics.
    * ``x in {a, b, c}`` (and tuple/list/dict-keys literals plus the empty
      constructor calls ``set()`` / ``tuple()`` / ``list()`` /
      ``frozenset()`` / ``dict()``) → expands to ``x == a or x == b or
      x == c`` so each disjunct becomes a flippable branch. ``not in``
      expands symmetrically to AND-of-``!=``. Empty containers fold to
      ``Constant(False)``; single-element containers collapse to a bare
      ``Compare(Eq)``; duplicate elements deduplicate via Python ``__eq__``
      on the underlying literal value. Non-literal comparators or any
      non-literal element skip the rewrite and the original Compare is
      returned unchanged.

    Optional ``state`` argument lets the engine receive telemetry counter
    bumps (``gen_membership_rewritten`` / ``gen_membership_skipped_non_literal``)
    at the rewrite site. Unit tests that drive the rewriter directly pass
    no state and assert only on AST shape.
    """

    def __init__(self, state: ExplorationState | None = None) -> None:
        super().__init__()
        self._state = state

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return node
        op = node.ops[0]
        comparator = node.comparators[0]
        if isinstance(op, ast.Is):
            if not _is_literal_comparator(comparator):
                return node
            return _build_helper_call_from_args(_IS_HELPER, [node.left, comparator], node)
        if isinstance(op, (ast.In, ast.NotIn)):
            return self._rewrite_membership(node, op, comparator)
        return node

    def _rewrite_membership(
        self,
        node: ast.Compare,
        op: ast.cmpop,
        comparator: ast.expr,
    ) -> ast.AST:
        elements = _literal_container_elements(comparator)
        if elements is None:
            self._bump_skip()
            return node
        deduped = _dedup_literal_elements(elements)
        if not deduped:
            self._bump_rewritten()
            return ast.copy_location(ast.Constant(value=isinstance(op, ast.NotIn)), node)
        eq_op: ast.cmpop = ast.NotEq() if isinstance(op, ast.NotIn) else ast.Eq()
        bool_op: ast.boolop = ast.And() if isinstance(op, ast.NotIn) else ast.Or()
        comparisons = [_build_eq_compare(node.left, elem, eq_op, node) for elem in deduped]
        self._bump_rewritten()
        if len(comparisons) == 1:
            return comparisons[0]
        return ast.copy_location(ast.BoolOp(op=bool_op, values=comparisons), node)

    def _bump_rewritten(self) -> None:
        if self._state is not None:
            self._state.gen_membership_rewritten += 1

    def _bump_skip(self) -> None:
        if self._state is not None:
            self._state.gen_membership_skipped_non_literal += 1


def _literal_container_elements(comparator: ast.expr) -> list[ast.expr] | None:
    """Return element nodes for a literal container, or ``None`` if not one.

    ``Dict`` returns keys to match Python's ``x in dict`` semantics; empty
    zero-arg constructor calls return ``[]``; non-literal elements (Name,
    Call, attribute access) disqualify the whole comparator.
    """
    if isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
        return list(comparator.elts) if all(map(_is_literal_element, comparator.elts)) else None
    if isinstance(comparator, ast.Dict):
        keys = [k for k in comparator.keys if k is not None]
        if len(keys) != len(comparator.keys):
            return None
        return keys if all(map(_is_literal_element, keys)) else None
    if _is_empty_container_call(comparator):
        return []
    return None


def _is_empty_container_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _EMPTY_CONSTRUCTOR_NAMES
        and not node.args
        and not node.keywords
    )


def _is_literal_element(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
    )


def _literal_element_value(node: ast.expr) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    assert isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant)
    return -node.operand.value


def _dedup_literal_elements(elements: list[ast.expr]) -> list[ast.expr]:
    """Deduplicate literal elements by their concrete value, preserving order.

    Uses an ``(type(value), value)`` key so ``1`` and ``True`` (which are
    Python-``==`` equal but semantically distinct under most callers'
    intent) collapse only when they share both type and value.
    """
    seen: list[tuple[type, Any]] = []
    out: list[ast.expr] = []
    for elem in elements:
        value = _literal_element_value(elem)
        key = (type(value), value)
        if key in seen:
            continue
        seen.append(key)
        out.append(elem)
    return out


def _build_eq_compare(
    left: ast.expr,
    right: ast.expr,
    op: ast.cmpop,
    anchor: ast.AST,
) -> ast.Compare:
    compare = ast.Compare(left=left, ops=[op], comparators=[right])
    return ast.copy_location(compare, anchor)


def _is_literal_comparator(comparator: ast.expr) -> bool:
    """Return True if ``comparator`` is a literal sentinel safe to rewrite.

    Uses identity comparison on the literal value so that ``0`` does not
    accidentally match ``False`` via Python's int/bool equivalence.
    """
    if not isinstance(comparator, ast.Constant):
        return False
    return any(comparator.value is sentinel for sentinel in _IS_REWRITE_LITERALS)


def rewrite_target(
    target: Callable[..., Any],
    state: ExplorationState | None = None,
) -> Callable[..., Any]:
    """Return a rewritten copy of ``target`` with concolic call dispatch.

    Applies both the Call and Compare rewriters to ``target``'s source,
    compiles against the original source filename so line numbers stay
    aligned for ``sys.settrace``, and execs the result in a shallow
    copy of the target's own ``__globals__`` with ``pyct`` injected so
    the fully-qualified helper references resolve. Copying the globals
    dict means the original target module is not mutated.

    The optional ``state`` argument lets the engine receive telemetry
    counter bumps from the Compare rewriter at the moment a membership
    rewrite fires or is skipped. Standalone callers (unit tests) pass
    no state and the counters are silently ignored.

    Lambdas are rejected upfront. ``inspect.getsource`` on a lambda
    returns the entire containing statement rather than just the
    ``lambda`` expression, which means ``exec``-ing the rewritten
    source would run the whole calling line — including, in the
    common case ``engine.explore(lambda x: ..., {...})``, a recursive
    call back into the engine. Named functions only.

    Raises:
        TypeError: if ``target`` is a lambda, has no inspectable source
            (built-in or C extension function), if the rewrite produces
            no top-level callable with ``target.__name__``, or if
            parsing/compilation fails. Engine.explore catches TypeError
            and returns a clean error_result, so the caller never sees a
            raw SyntaxError / KeyError escape the engine.
    """
    if target.__name__ == "<lambda>":
        raise TypeError(
            "cannot rewrite lambda targets — inspect.getsource returns the "
            "containing statement, not the lambda body. Define the target "
            "as a named function at module or test-module level."
        )

    try:
        tree, filename = _parse_rewritten_tree(target, state)
    except SyntaxError as exc:
        raise TypeError(f"rewrite failed to parse {target.__name__}: {exc}") from exc

    if not _tree_defines_name(tree, target.__name__):
        raise TypeError(
            f"rewrite of {target.__name__} produced no top-level definition "
            f"(source was: {ast.unparse(tree)[:80]!r}); "
            "inline or nested closures are not supported"
        )

    code = compile(tree, filename, "exec")
    exec_globals = _build_exec_globals(target)
    namespace: dict[str, Any] = {}
    exec(code, exec_globals, namespace)  # noqa: S102

    rewritten = namespace.get(target.__name__)
    if rewritten is None:
        raise TypeError(
            f"rewrite of {target.__name__} produced no top-level callable "
            f"after exec; parsed tree validated but name did not bind"
        )
    rewritten.__wrapped__ = target
    return rewritten


def _tree_defines_name(tree: ast.Module, name: str) -> bool:
    """Return True if ``tree`` has a top-level FunctionDef or AsyncFunctionDef with ``name``."""
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


def _parse_rewritten_tree(
    target: Callable[..., Any],
    state: ExplorationState | None = None,
) -> tuple[ast.Module, str]:
    """Return ``(transformed_tree, source_filename)`` for ``target``.

    Extracted from rewrite_target so the parse + transform step can
    raise SyntaxError cleanly without tripping the exec validation that
    runs afterward.
    """
    source = textwrap.dedent(inspect.getsource(target))
    filename = inspect.getfile(inspect.unwrap(target))

    tree = ast.parse(source, filename=filename)
    tree = ConcolicCallRewriter().visit(tree)
    tree = ConcolicCompareRewriter(state=state).visit(tree)
    ast.fix_missing_locations(tree)
    _shift_line_numbers(tree, target)
    return tree, filename


def _build_exec_globals(target: Callable[..., Any]) -> dict[str, Any]:
    """Return a globals dict for ``exec`` that resolves helper imports.

    The rewritten source references ``pyct.core.builtin_wrappers._int``
    and similar fully-qualified paths. These resolve via attribute
    lookup starting from ``pyct`` in the function's globals. We inject
    ``pyct`` into a shallow copy so the target's real module globals
    are not mutated, and we eagerly import the helper submodules so
    they're accessible as attributes of the ``pyct`` package.
    """
    import pyct  # noqa: PLC0415 — deferred import avoids a top-level cycle
    import pyct.core.builtin_wrappers  # noqa: F401, PLC0415
    import pyct.core.concolic_range  # noqa: F401, PLC0415

    exec_globals = dict(inspect.unwrap(target).__globals__)
    exec_globals["pyct"] = pyct
    return exec_globals


def _build_helper_call(helper_dotted: str, original: ast.Call) -> ast.Call:
    """Build ``helper(*original.args)`` preserving line numbers."""
    return _build_helper_call_from_args(helper_dotted, original.args, original)


def _build_helper_call_from_args(
    helper_dotted: str,
    args: list[ast.expr],
    anchor: ast.AST,
) -> ast.Call:
    """Build ``helper(*args)`` using ``anchor``'s line number."""
    template = ast.parse(f"{helper_dotted}()", mode="eval").body
    assert isinstance(template, ast.Call)
    template.args = args
    template.keywords = []
    ast.copy_location(template, anchor)
    for node in ast.walk(template.func):
        ast.copy_location(node, anchor)
    return template


def _shift_line_numbers(tree: ast.AST, target: Callable[..., Any]) -> None:
    """Rewrite line numbers so they match the original source file.

    ``inspect.getsource`` returns a dedented snippet starting at line 1,
    but ``sys.settrace`` reports line numbers from the ORIGINAL file.
    After parsing we need to add the def-line offset back so the
    compiled code's line numbers align with the source file on disk.
    If ``inspect.getsourcelines`` fails here even though ``getsource``
    succeeded upstream, coverage attribution for this target would be
    silently empty — we log a WARNING rather than failing the run so
    the issue has at least a breadcrumb in the log.
    """
    try:
        _source_lines, start_line = inspect.getsourcelines(target)
    except (OSError, TypeError) as exc:
        log.warning(
            "line shift unavailable for %s: %s; coverage attribution may be empty",
            getattr(target, "__qualname__", target.__name__),
            exc,
        )
        return
    offset = start_line - 1
    if offset == 0:
        return
    for node in ast.walk(tree):
        if hasattr(node, "lineno"):
            node.lineno += offset
        if hasattr(node, "end_lineno") and node.end_lineno is not None:
            node.end_lineno += offset
