"""Turn ``module::function`` into the callable it names."""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from pyct.run.threads import running


class TargetError(Exception):
    """The target could not be loaded: the module does not import or lacks the function."""


@dataclass(frozen=True)
class Target:
    """A loaded target: its spec, the callable, the file it lives in, and its signature.

    ``threads`` is how many threads the target's import left running in this
    process, beyond those running before it, as the system counts them.
    """

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature
    threads: int = 0


def load_target(spec: str) -> Target:
    """Import ``module`` from the current directory and take ``function`` from it.

    The working directory goes first on the import path, so a module under
    it resolves with no ``PYTHONPATH`` set. The threads running are counted
    just before the import and just after it, so the target knows how many
    the import left running.
    """
    module_name, function_name = spec.split("::", 1)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    before = running()
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise TargetError(f"cannot import {module_name}: {error!r}") from error
    threads = max(running() - before, 0)
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise TargetError(f"{module_name} has no function {function_name}")
    file = getattr(module, "__file__", None)
    if file is None or not file.endswith(".py"):
        raise TargetError(f"{module_name} has no Python source file")
    signature = inspect.signature(fn)
    return Target(spec=spec, fn=fn, file=file, signature=signature, threads=threads)
