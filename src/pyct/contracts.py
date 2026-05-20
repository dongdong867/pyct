"""Native ``@pre`` / ``@post`` contract decorators + discovery.

Public surface:

- ``@pre("CONDITION")`` / ``@post("CONDITION")`` attach a frozen
  ``ContractSet`` to the decorated function's ``__pyct_contracts__``
  attribute. Decorators are attach-attr only — they return the
  original function unchanged, so ``f is original_f`` after decoration.
- ``Contract`` / ``ContractSet`` describe the discovered metadata.
- ``EMPTY_CONTRACTS`` is the singleton returned for undecorated
  targets (identity-preserving — callers can use ``is`` checks).
- ``discover_contracts(target)`` reads ``__pyct_contracts__`` via
  ``getattr`` with ``EMPTY_CONTRACTS`` as the default.
- ``PyCTContractSyntaxError`` is raised at decoration time on
  unparseable predicate strings; it subclasses ``SyntaxError`` so
  it surfaces loudly at module import.

Predicates are string literals (not lambdas) — eagerly compiled at
decoration time and wrapped in a callable that closes over the target
function and evaluates as ``eval(code, target.__globals__, kwargs)``
so builtins and module-level constants resolve naturally.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Contract:
    """A single precondition or postcondition discovered on a target.

    Attributes:
        predicate: Callable invoked as ``predicate(**bound)`` where
            ``bound`` is the subset of the engine's concrete args
            named in ``condition_args``. Must return a truthy value
            when the contract holds.
        description: Raw predicate source string, used in violation
            messages. Always populated by the native decorator path.
        source: ``"path:line"`` location captured at decoration time
            via ``inspect.stack()``; surfaced verbatim in violation
            strings emitted by ``_check_preconditions``.
        condition_args: Subset of the target's parameter names that
            the predicate references. Names outside the signature
            (builtins, module globals, ``__return__``) are excluded.
    """

    predicate: Callable[..., Any]
    description: str
    source: str
    condition_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractSet:
    """Aggregated preconditions + postconditions discovered on a target."""

    requires: tuple[Contract, ...] = field(default_factory=tuple)
    ensures: tuple[Contract, ...] = field(default_factory=tuple)


EMPTY_CONTRACTS = ContractSet()


class PyCTContractSyntaxError(SyntaxError):
    """Raised when a ``@pre`` / ``@post`` predicate string fails to parse.

    Subclasses ``SyntaxError`` so an invalid contract on a module-level
    function fails the entire module import loudly — there is no silent
    "skip the broken contract" path.
    """


def discover_contracts(target: Any) -> ContractSet:
    """Return the ``ContractSet`` attached to ``target``, or ``EMPTY_CONTRACTS``.

    The native decorators populate ``target.__pyct_contracts__`` at
    decoration time; this reader is a thin ``getattr`` over that
    attribute. Targets without contracts return the singleton
    ``EMPTY_CONTRACTS`` (identity-preserving so callers can use
    ``is`` checks).
    """
    return getattr(target, "__pyct_contracts__", EMPTY_CONTRACTS)


def pre(condition: str) -> Callable[[Callable], Callable]:
    """Attach a precondition predicate to the decorated function.

    The decorator returns the *original* function unchanged with a
    fresh ``ContractSet`` placed on ``__pyct_contracts__``. Stacking
    ``@pre`` decorators prepends each new contract so source-order
    top-to-bottom corresponds to first-to-last in the ``requires``
    tuple.
    """
    if not isinstance(condition, str):
        raise TypeError(
            f"@pre expects a string predicate; got {type(condition).__name__}"
        )
    source = _capture_call_site()
    return _build_decorator(condition, source, kind="require")


def post(condition: str) -> Callable[[Callable], Callable]:
    """Attach a postcondition predicate to the decorated function.

    Predicates may reference the return value as ``__return__``; the
    shorthand ``_`` is rewritten to ``__return__`` at decoration time
    so the compiled code object always references the canonical name.
    """
    if not isinstance(condition, str):
        raise TypeError(
            f"@post expects a string predicate; got {type(condition).__name__}"
        )
    source = _capture_call_site()
    return _build_decorator(condition, source, kind="ensure")


def _build_decorator(
    condition: str,
    source: str,
    *,
    kind: str,
) -> Callable[[Callable], Callable]:
    """Return a decorator that attaches a freshly compiled contract."""

    def decorator(target: Callable) -> Callable:
        contract = _compile_contract(condition, source, target, kind=kind)
        existing = getattr(target, "__pyct_contracts__", EMPTY_CONTRACTS)
        if kind == "require":
            updated = ContractSet(
                requires=(contract, *existing.requires),
                ensures=existing.ensures,
            )
        else:
            updated = ContractSet(
                requires=existing.requires,
                ensures=(contract, *existing.ensures),
            )
        target.__pyct_contracts__ = updated  # type: ignore[attr-defined]
        return target

    return decorator


def _compile_contract(
    condition: str,
    source: str,
    target: Callable,
    *,
    kind: str,
) -> Contract:
    """Compile ``condition`` into a Contract bound to ``target``'s globals.

    Postcondition predicates are normalized so ``_`` rewrites to
    ``__return__`` before ``compile()`` runs — both surface forms
    produce identical code objects downstream.
    """
    if kind == "ensure":
        code = _compile_predicate_with_underscore_normalization(condition)
    else:
        code = _compile_predicate(condition)

    parameters = _target_parameters(target)
    condition_args = tuple(name for name in code.co_names if name in parameters)
    predicate = _make_predicate(code, target)

    return Contract(
        predicate=predicate,
        description=condition,
        source=source,
        condition_args=condition_args,
    )


def _compile_predicate(expr: str):
    """Compile ``expr`` as a Python expression, mapping SyntaxError loudly."""
    try:
        return compile(expr, "<contract>", "eval")
    except SyntaxError as exc:
        raise PyCTContractSyntaxError(str(exc)) from exc


def _compile_predicate_with_underscore_normalization(expr: str):
    """Compile ``expr`` after rewriting `_` references to ``__return__``."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise PyCTContractSyntaxError(str(exc)) from exc
    _UnderscoreToReturn().visit(tree)
    ast.fix_missing_locations(tree)
    return compile(tree, "<contract>", "eval")


class _UnderscoreToReturn(ast.NodeTransformer):
    """Rewrite ``Name(id='_')`` references to the canonical ``__return__``."""

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802 — ast hook name
        if node.id == "_":
            return ast.copy_location(
                ast.Name(id="__return__", ctx=node.ctx), node
            )
        return node


def _target_parameters(target: Callable) -> set[str]:
    """Return the parameter names declared in ``target``'s signature.

    Targets without an introspectable signature (builtins, C extensions)
    contribute an empty set — ``condition_args`` collapses to ``()`` and
    every predicate name resolves at eval time via ``__globals__``.
    """
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return set()
    return set(sig.parameters)


def _make_predicate(code, target: Callable) -> Callable[..., Any]:
    """Wrap ``code`` in a callable closing over ``target.__globals__``.

    Using the target's globals as the ``eval`` ``globals`` argument is
    what makes module-level constants and imported names resolve from
    the target's defining module — without it, predicates would only
    see builtins plus the kwargs the engine binds.

    Exposes the compiled code object as ``predicate.__code__`` so
    callers (engine, tests) can introspect ``co_names`` after the
    underscore normalization pass.
    """
    return _PredicateCallable(code, getattr(target, "__globals__", {}))


class _PredicateCallable:
    """Callable wrapper exposing the compiled predicate's code object."""

    __slots__ = ("__code__", "_globals")

    def __init__(self, code, target_globals: dict[str, Any]) -> None:
        self.__code__ = code
        self._globals = target_globals

    def __call__(self, **kwargs: Any) -> Any:
        return eval(  # noqa: S307 — string predicate intent
            self.__code__, self._globals, kwargs
        )


def _capture_call_site() -> str:
    """Return ``"path:line"`` of the call frame that invoked ``pre``/``post``."""
    frame = inspect.stack()[2]  # 0=this fn, 1=pre/post, 2=user decorator line
    return f"{frame.filename}:{frame.lineno}"


__all__ = (
    "pre",
    "post",
    "Contract",
    "ContractSet",
    "EMPTY_CONTRACTS",
    "discover_contracts",
    "PyCTContractSyntaxError",
)
