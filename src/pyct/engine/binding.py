"""Binding table — maps solver variables to primitives nested in arguments.

A dict, list or object argument reaches the target with its primitive
leaves invisible to the solver: ``config["server"]["port"]`` is a plain
``int``, so ``port > 65535`` evaluates concretely and no constraint is
recorded. The binding table fixes that by giving every leaf its own SMT
variable, keyed by the *route* that reaches it.

The table is built once from the seed arguments and used three ways:

* ``binding_var_types`` declares the variables to the solver
* ``wrap_leaves`` names the leaves so branch conditions become symbolic
* ``apply_model`` writes a solver model back into a nested structure

All three assume the argument *shape* is fixed for the run. Values
change; keys, indices and attributes do not. Questions about shape —
whether a key exists, how long a list is — are outside what this
answers, and stay concrete.
"""

from __future__ import annotations

import copy
import logging
import types
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pyct.utils.concolic_converter import wrap_concolic

log = logging.getLogger("ct.engine.binding")

SegmentKind = Literal["key", "index", "attr"]

_VAR_SUFFIX = "_VAR"

# Looked up by exact type, so ``bool`` resolves to Bool rather than Int
# despite subclassing it.
_SORT_BY_TYPE: dict[type, str] = {
    bool: "Bool",
    int: "Int",
    float: "Real",
    str: "String",
}

# Values that own a ``__dict__`` but are not data worth walking.
_OPAQUE_TYPES = (
    type,
    types.ModuleType,
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
)


@dataclass(frozen=True)
class Segment:
    """One step from a parameter toward a primitive leaf.

    ``kind`` selects how ``value`` is used: a dict key, a sequence
    index, or an attribute name.
    """

    kind: SegmentKind
    value: Any


@dataclass(frozen=True)
class Leaf:
    """A solver variable bound to one primitive inside an argument.

    ``route`` is empty when the parameter is itself a primitive, in
    which case ``var`` keeps the historical ``{param}_VAR`` name so
    existing constraint text is unchanged.
    """

    var: str
    param: str
    route: tuple[Segment, ...]
    sort: str

    @property
    def model_key(self) -> str:
        """Name this variable carries in a *parsed* solver model.

        ``ModelParser`` strips the ``_VAR`` suffix when it reads solver
        output, so a model is keyed by the bare name while declarations
        and constraint text use ``var``. Looking a model up by ``var``
        silently finds nothing.
        """
        if self.var.endswith(_VAR_SUFFIX):
            return self.var[: -len(_VAR_SUFFIX)]
        return self.var


def build_binding(args: dict[str, Any]) -> tuple[Leaf, ...]:
    """Return one Leaf per solvable primitive reachable from ``args``.

    A parameter whose value cannot be deep-copied contributes no leaves:
    ``apply_model`` and ``wrap_leaves`` both copy before writing, so a
    parameter they cannot copy has to stay concrete. Dropping it here
    means the decision is made once, at build time, rather than raising
    on every iteration.
    """
    leaves: list[Leaf] = []
    for param, value in args.items():
        found = _leaves_for_param(param, value)
        if found and not _is_copyable(value):
            log.debug("parameter %r cannot be copied; leaving it concrete", param)
            continue
        leaves.extend(found)
    return tuple(leaves)


def binding_var_types(binding: tuple[Leaf, ...]) -> dict[str, str]:
    """Return the ``{variable: SMT sort}`` mapping the solver needs."""
    return {leaf.var: leaf.sort for leaf in binding}


def apply_model(
    args: dict[str, Any],
    binding: tuple[Leaf, ...],
    model: dict[str, Any],
) -> dict[str, Any]:
    """Return ``args`` with the model's values written at their routes.

    Solver models are flat and partial: they name variables, not nested
    positions, and mention only the variables the constraint constrained.
    Leaves the model does not mention keep their current value, which is
    why the previous arguments are the starting point rather than a
    structure built from scratch.

    Lookups go through ``Leaf.model_key``, not ``Leaf.var`` — the parser
    has already stripped the ``_VAR`` suffix by this point.
    """
    return _rebuild(args, binding, lambda leaf, current: model.get(leaf.model_key, current))


def wrap_leaves(
    args: dict[str, Any],
    binding: tuple[Leaf, ...],
    engine: Any | None,
) -> dict[str, Any]:
    """Return ``args`` with every bound leaf replaced by a Concolic value.

    The wrapper carries the leaf's variable name as its expression, so a
    comparison against it records a constraint the solver can flip.
    """
    return _rebuild(args, binding, lambda leaf, current: wrap_concolic(current, leaf.var, engine))


def _leaves_for_param(param: str, value: Any) -> list[Leaf]:
    """Return the leaves reachable from a single parameter."""
    routes = _walk(value, (), frozenset())
    if routes and routes[0][0] == ():
        return [Leaf(f"{param}{_VAR_SUFFIX}", param, (), routes[0][1])]
    return [
        Leaf(f"{param}__L{index}{_VAR_SUFFIX}", param, route, sort)
        for index, (route, sort) in enumerate(routes)
    ]


def _walk(
    value: Any,
    route: tuple[Segment, ...],
    seen: frozenset[int],
) -> list[tuple[tuple[Segment, ...], str]]:
    """Return ``(route, sort)`` for every solvable primitive under ``value``.

    ``seen`` tracks container identity so a self-referencing structure
    terminates. Identity rather than depth, so a legitimately deep
    structure is still walked in full.
    """
    sort = _SORT_BY_TYPE.get(type(value))
    if sort is not None:
        return [(route, sort)]
    if id(value) in seen:
        return []
    nested = seen | {id(value)}
    return [
        found
        for segment, child in _children(value)
        for found in _walk(child, (*route, segment), nested)
    ]


def _children(value: Any) -> list[tuple[Segment, Any]]:
    """Return the ``(segment, child)`` pairs one step below ``value``."""
    if isinstance(value, dict):
        return [(Segment("key", key), item) for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        return [(Segment("index", index), item) for index, item in enumerate(value)]
    return _attribute_children(value)


def _attribute_children(value: Any) -> list[tuple[Segment, Any]]:
    """Return attribute children for a plain object, or none for opaque values."""
    if isinstance(value, _OPAQUE_TYPES):
        return []
    if hasattr(value, "__dict__"):
        return [(Segment("attr", name), item) for name, item in vars(value).items()]
    return [
        (Segment("attr", name), getattr(value, name))
        for name in getattr(value, "__slots__", ())
        if hasattr(value, name)
    ]


def _is_copyable(value: Any) -> bool:
    """Return True when ``value`` survives a deep copy."""
    try:
        copy.deepcopy(value)
    except Exception:  # noqa: BLE001 — any failure means "leave it concrete"
        return False
    return True


def _rebuild(
    args: dict[str, Any],
    binding: tuple[Leaf, ...],
    value_for: Callable[[Leaf, Any], Any],
) -> dict[str, Any]:
    """Copy the parameters that own leaves and rewrite each leaf in place.

    Parameters with no leaves pass through by reference — they hold
    nothing the solver can change, and copying them would fail on values
    like locks or file handles.
    """
    touched = {leaf.param for leaf in binding}
    out = {
        name: (copy.deepcopy(value) if name in touched else value) for name, value in args.items()
    }
    for leaf in binding:
        _write(out, leaf, value_for(leaf, _read(out, leaf)))
    return out


def _read(out: dict[str, Any], leaf: Leaf) -> Any:
    """Return the value currently sitting at ``leaf``'s route."""
    current = out[leaf.param]
    for segment in leaf.route:
        current = _step(current, segment)
    return current


def _write(out: dict[str, Any], leaf: Leaf, value: Any) -> None:
    """Write ``value`` at ``leaf``'s route."""
    if not leaf.route:
        out[leaf.param] = value
        return
    container = out[leaf.param]
    for segment in leaf.route[:-1]:
        container = _step(container, segment)
    _assign(container, leaf.route[-1], value)


def _step(container: Any, segment: Segment) -> Any:
    """Descend one segment into ``container``."""
    if segment.kind == "attr":
        return getattr(container, segment.value)
    return container[segment.value]


def _assign(container: Any, segment: Segment, value: Any) -> None:
    """Set ``value`` at ``segment`` within ``container``.

    Uses ``object.__setattr__`` so frozen dataclasses are writable —
    the instance is already a private copy, so bypassing the freeze
    cannot be observed by the caller.
    """
    if segment.kind == "attr":
        object.__setattr__(container, segment.value, value)
    else:
        container[segment.value] = value
