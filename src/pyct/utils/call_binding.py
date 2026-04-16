"""Signature-aware call helper.

PyCT invokes user-provided targets with an argument *dict* — initial
args, concolic-wrapped args, LLM-generated seed dicts. The naive
``target(**args)`` call fails when a parameter is positional-only
(PEP 570, ``/`` separator in the signature): Python raises
``TypeError: got some positional-only arguments passed as keyword
arguments``. Targets like ``validators.url(value: str, /, ...)`` and
many stdlib functions hit this.

``call_with_args`` inspects the signature and routes each entry to
the correct call slot — positional list or keyword dict. It also:

* drops keys that aren't parameters of the target (defensive — LLMs
  occasionally hallucinate extra keys);
* drops values that obviously violate a ``Callable`` annotation
  (e.g. the LLM emits ``None`` for a callable-default parameter),
  letting the target's real default take effect.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any


def call_with_args(func: Callable[..., Any], args: dict[str, Any]) -> Any:
    """Call ``func`` with the entries in ``args`` routed to the right slots.

    Positional-only parameters receive values positionally (in signature
    order); all other parameters receive values by keyword. Entries
    whose name isn't a parameter of ``func`` are silently dropped.
    Values that violate a ``Callable`` annotation are also dropped, so
    the target's default callable is used.
    """
    sig = inspect.signature(func)
    hints = _resolve_hints(func)
    positional, keyword = _split_args(sig, hints, args)
    return func(*positional, **keyword)


def _resolve_hints(func: Callable[..., Any]) -> dict[str, Any]:
    """Return annotation → type map; empty dict on resolution failure."""
    try:
        return typing.get_type_hints(func)
    except Exception:
        return {}


def _split_args(
    sig: inspect.Signature,
    hints: dict[str, Any],
    args: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    """Split ``args`` into ``(positional, keyword)`` per ``sig``."""
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name not in args:
            continue
        value = args[name]
        if _violates_callable_annotation(hints.get(name), value):
            continue
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        elif param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            keyword[name] = value
    return positional, keyword


def _violates_callable_annotation(annotation: Any, value: Any) -> bool:
    """True if ``annotation`` is ``Callable`` but ``value`` isn't callable."""
    if not _is_callable_annotation(annotation):
        return False
    return not callable(value)


def _is_callable_annotation(annotation: Any) -> bool:
    """True if ``annotation`` denotes a ``Callable`` type.

    Accepts both ``typing.Callable[...]`` and
    ``collections.abc.Callable`` (bare or subscripted).
    """
    if annotation is Callable:
        return True
    origin = typing.get_origin(annotation)
    return origin is Callable or origin is typing.Callable
