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
from typing import Any

log = logging.getLogger("ct.engine.ast_transformer")

_INT_HELPER = "pyct.core.builtin_wrappers._int"
_STR_HELPER = "pyct.core.builtin_wrappers._str"
_IS_HELPER = "pyct.core.builtin_wrappers._is"
_RANGE_CLASS = "pyct.core.concolic_range.ConcolicRange"


class ConcolicCallRewriter(ast.NodeTransformer):
    """Rewrites ``int(x)``, ``str(x)``, ``range(...)`` Call nodes."""

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
        return node


_IS_REWRITE_LITERALS = (None, True, False, Ellipsis)


class ConcolicCompareRewriter(ast.NodeTransformer):
    """Rewrites ``x is <literal>`` Compare nodes for concolic unwrap checks.

    Only rewrites when the comparator is a sentinel literal — ``None``,
    ``True``, ``False``, or ``Ellipsis``. These are the 99% idiom
    (``x is None``) where unwrapping the concolic side to check against
    the sentinel matches the author's intent.

    Variable-RHS ``is`` checks (``x is y``) are left untouched because
    the concolic layer can't preserve Python's object-identity semantics
    — two wrappers of the same primitive would test identical under a
    naive unwrap-and-compare, which is wrong for any target relying on
    genuine identity.
    """

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return node
        if not isinstance(node.ops[0], ast.Is):
            return node
        if not _is_literal_comparator(node.comparators[0]):
            return node
        return _build_helper_call_from_args(_IS_HELPER, [node.left, node.comparators[0]], node)


def _is_literal_comparator(comparator: ast.expr) -> bool:
    """Return True if ``comparator`` is a literal sentinel safe to rewrite.

    Uses identity comparison on the literal value so that ``0`` does not
    accidentally match ``False`` via Python's int/bool equivalence.
    """
    if not isinstance(comparator, ast.Constant):
        return False
    return any(comparator.value is sentinel for sentinel in _IS_REWRITE_LITERALS)


def rewrite_target(target: Callable[..., Any]) -> Callable[..., Any]:
    """Return a rewritten copy of ``target`` with concolic call dispatch.

    Applies both the Call and Compare rewriters to ``target``'s source,
    compiles against the original source filename so line numbers stay
    aligned for ``sys.settrace``, and execs the result in a shallow
    copy of the target's own ``__globals__`` with ``pyct`` injected so
    the fully-qualified helper references resolve. Copying the globals
    dict means the original target module is not mutated.

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
        tree, filename = _parse_rewritten_tree(target)
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


def _parse_rewritten_tree(target: Callable[..., Any]) -> tuple[ast.Module, str]:
    """Return ``(transformed_tree, source_filename)`` for ``target``.

    Extracted from rewrite_target so the parse + transform step can
    raise SyntaxError cleanly without tripping the exec validation that
    runs afterward.
    """
    source = textwrap.dedent(inspect.getsource(target))
    filename = inspect.getfile(inspect.unwrap(target))

    tree = ast.parse(source, filename=filename)
    tree = ConcolicCallRewriter().visit(tree)
    tree = ConcolicCompareRewriter().visit(tree)
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
