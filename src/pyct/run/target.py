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
    """``fn``'s signature. Any Exception ``inspect.signature`` raises is a ``TargetError``.

    Reading a signature can run the target's own code, such as an attribute
    lookup or, from Python 3.14, an annotation's evaluation, so any
    Exception can come of it. The refusal gives ``_reason`` for it.
    """
    try:
        return inspect.signature(fn)
    except Exception as error:
        raise TargetError(f"cannot read the signature of {spec}: {_reason(error)}") from error


def _reason(error: BaseException) -> str:
    """Python's message for ``error`` as one line that is never empty.

    That is the message's first line that holds anything, or the
    exception's type name when no line does, so the refusal stays one
    line on stderr.
    """
    for line in str(error).splitlines():
        if line.strip():
            return line
    return type(error).__name__
