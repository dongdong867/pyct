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
import textwrap
from collections.abc import Callable
from typing import Any

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


class ConcolicCompareRewriter(ast.NodeTransformer):
    """Rewrites ``x is y`` Compare nodes with a single ``is`` operator."""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) != 1 or len(node.comparators) != 1:
            return node
        if not isinstance(node.ops[0], ast.Is):
            return node
        return _build_helper_call_from_args(_IS_HELPER, [node.left, node.comparators[0]], node)


def rewrite_target(target: Callable[..., Any]) -> Callable[..., Any]:
    """Return a rewritten copy of ``target`` with concolic call dispatch.

    Applies both the Call and Compare rewriters to ``target``'s source,
    compiles against the original source filename so line numbers stay
    aligned for ``sys.settrace``, and execs the result in a shallow
    copy of the target's own ``__globals__`` with ``pyct`` injected so
    the fully-qualified helper references resolve. Copying the globals
    dict means the original target module is not mutated.

    Raises:
        TypeError: if ``target`` has no inspectable source (built-in
            or C extension function).
    """
    code = _compile_rewritten_source(target)
    exec_globals = _build_exec_globals(target)
    namespace: dict[str, Any] = {}
    exec(code, exec_globals, namespace)  # noqa: S102
    rewritten = namespace[target.__name__]
    rewritten.__wrapped__ = target
    return rewritten


def _compile_rewritten_source(target: Callable[..., Any]) -> Any:
    """Parse ``target``'s source, apply rewriters, and compile to a code object."""
    source = textwrap.dedent(inspect.getsource(target))
    try:
        filename = inspect.getfile(target)
    except TypeError:
        filename = "<rewritten>"

    tree = ast.parse(source, filename=filename)
    tree = ConcolicCallRewriter().visit(tree)
    tree = ConcolicCompareRewriter().visit(tree)
    ast.fix_missing_locations(tree)
    _shift_line_numbers(tree, target)
    return compile(tree, filename, "exec")


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

    exec_globals = dict(target.__globals__)
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
    """
    try:
        _source_lines, start_line = inspect.getsourcelines(target)
    except (OSError, TypeError):
        return
    offset = start_line - 1
    if offset == 0:
        return
    for node in ast.walk(tree):
        if hasattr(node, "lineno"):
            node.lineno += offset
        if hasattr(node, "end_lineno") and node.end_lineno is not None:
            node.end_lineno += offset
