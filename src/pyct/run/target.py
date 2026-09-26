"""Turn ``module::function`` into the callable it names."""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass


class TargetError(Exception):
    """The target could not be loaded: the module does not import or lacks the function."""


@dataclass(frozen=True)
class Target:
    """A loaded target: its spec, the callable, the file it lives in, and its signature."""

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature


def load_target(spec: str) -> Target:
    """Import ``module`` from the current directory and take ``function`` from it.

    The working directory goes first on the import path, so a module under
    it resolves with no ``PYTHONPATH`` set.
    """
    module_name, function_name = spec.split("::", 1)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        module = importlib.import_module(module_name)
    except Exception as error:
        raise TargetError(f"cannot import {module_name}: {error!r}") from error
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise TargetError(f"{module_name} has no function {function_name}")
    file = getattr(module, "__file__", None)
    if file is None or not file.endswith(".py"):
        raise TargetError(f"{module_name} has no Python source file")
    return Target(spec=spec, fn=fn, file=file, signature=inspect.signature(fn))
