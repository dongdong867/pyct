"""Argument resolution — wraps initial args into Concolic types for the loop."""

from __future__ import annotations

from typing import Any

from pyct.engine.binding import wrap_leaves


def wrap_arguments(args: dict[str, Any], engine: Any) -> dict[str, Any]:
    """Return a new dict where each bound leaf is wrapped in a Concolic type.

    The wrapped value carries the engine reference, so operator overloads
    on the Concolic type can register branches back with ``engine.path``.

    Which values get wrapped is decided by the engine's binding table,
    built once from the seed arguments. Primitives nested inside dicts,
    lists and objects each get their own solver variable; anything the
    table does not cover — ``None``, ``bytes``, sets, uncopyable values —
    passes through unchanged and the target uses it concretely.
    """
    return wrap_leaves(args, engine._binding, engine)
