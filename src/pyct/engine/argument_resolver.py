"""Argument resolution — wraps initial args into Concolic types for the loop."""

from __future__ import annotations

from typing import Any

from pyct.utils.concolic_converter import wrap_concolic

_SMT_TYPE_BY_PY_TYPE: dict[type, str] = {
    bool: "Bool",
    int: "Int",
    float: "Real",
    str: "String",
}

_VAR_SUFFIX = "_VAR"


def wrap_arguments(args: dict[str, Any], engine: Any) -> dict[str, Any]:
    """Return a new dict where each value is wrapped in a Concolic type.

    The wrapped value carries the engine reference, so operator overloads
    on the Concolic type can register branches back with ``engine.path``.
    Non-wrappable values (collections, custom objects) pass through
    unchanged — the target function can still use them concretely.
    """
    return {
        name: wrap_concolic(value, f"{name}{_VAR_SUFFIX}", engine) for name, value in args.items()
    }


def build_var_to_types(args: dict[str, Any]) -> dict[str, str]:
    """Return the ``var_to_types`` mapping the solver needs.

    Keys are ``{name}_VAR`` strings, values are SMT type names. Entries
    whose Python type has no SMT counterpart are silently skipped — the
    solver won't be asked about them.
    """
    result: dict[str, str] = {}
    for name, value in args.items():
        smt_type = _SMT_TYPE_BY_PY_TYPE.get(type(value))
        if smt_type is not None:
            result[f"{name}{_VAR_SUFFIX}"] = smt_type
    return result
