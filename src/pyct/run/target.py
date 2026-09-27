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

# the two exceptions inspect raises when it cannot read a signature; one of exactly these types
# reads by its message alone
_INSPECT_S_OWN = (ValueError, TypeError)


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
    """``fn``'s signature. A raise or a ``SystemExit`` as it is read is a ``TargetError``.

    Reading a signature can run the target's own code, such as an attribute
    lookup or, from Python 3.14, an annotation's evaluation, so any
    Exception can come of it, or a SystemExit. The refusal gives ``_reason``
    for it. A KeyboardInterrupt, or pyct's own stop, goes on to end pyct.
    """
    try:
        return inspect.signature(fn)
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot read the signature of {spec}: {_reason(error)}") from error


def _reason(error: BaseException) -> str:
    """Python's message for ``error`` as one line that is never empty.

    That is the message's first line that holds anything. A ValueError or a
    TypeError reads by that line alone, as inspect's own refusals do; any
    other exception, a subclass of those two included, is named before it,
    as ``SystemExit: 0`` and ``UnicodeError: bad text``. A message with no
    such line gives the type's name alone, and so does one that cannot be
    read, since its ``__str__`` raises. So the refusal stays one line on
    stderr.
    """
    named = type(error).__name__
    try:
        message = str(error)
    except Exception:
        return named
    lines = [line for line in message.splitlines() if line.strip()]
    if not lines:
        return named
    return lines[0] if type(error) in _INSPECT_S_OWN else f"{named}: {lines[0]}"
