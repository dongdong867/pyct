"""Turn ``module::function`` into the callable it names."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from pyct.run.import_watch import ImportWatch


class TargetError(Exception):
    """The target could not be loaded, and the message says why.

    The module does not import, lacks the function, or has no Python source,
    or Python cannot read the function's signature.
    """


@dataclass(frozen=True)
class Target:
    """A loaded target: its spec, the callable, the file it lives in, and its signature."""

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature


def load_target(spec: str, watch: ImportWatch | None = None) -> Target:
    """Import ``module`` from the current directory and take ``function`` from it.

    The working directory goes first on the import path, so a module under
    it resolves with no ``PYTHONPATH`` set. While the module imports,
    ``watch`` names it for the process that watches this one, when one does.
    """
    module_name, function_name = spec.split("::", 1)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    module = _imported(module_name, watch)
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise TargetError(f"{module_name} has no function {function_name}")
    file = getattr(module, "__file__", None)
    if file is None or not file.endswith(".py"):
        raise TargetError(f"{module_name} has no Python source file")
    return Target(spec=spec, fn=fn, file=file, signature=_signature(spec, fn))


def _imported(module_name: str, watch: ImportWatch | None) -> ModuleType:
    """The module, imported. A raise or a ``SystemExit`` at its import is a ``TargetError``.

    Either reads by its repr. A KeyboardInterrupt goes on to end pyct, as a
    Ctrl-C does.
    """
    importing = contextlib.nullcontext() if watch is None else watch.importing(module_name)
    try:
        with importing:
            return importlib.import_module(module_name)
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot import {module_name}: {error!r}") from error


def _signature(spec: str, fn: Callable[..., object]) -> inspect.Signature:
    """``fn``'s signature. One ``inspect.signature`` cannot read is a ``TargetError``.

    ``inspect.signature`` says so by ValueError or TypeError, and its message
    is the reason the refusal gives.
    """
    try:
        return inspect.signature(fn)
    except (ValueError, TypeError) as error:
        raise TargetError(f"cannot read the signature of {spec}: {error}") from error
