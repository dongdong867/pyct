"""The names a class or a module holds in its own namespace, and the file a module names there,
read by the value's type alone, so that no attribute hook of the target's classes or lazy
modules runs in pyct's process."""

from __future__ import annotations

import types
from collections.abc import Mapping

# the descriptors that hold a class's and a module's own namespace, read by ``type`` and
# ``types.ModuleType`` themselves, whatever the class of the value they read
_CLASS_NAMES = vars(type)["__dict__"]
_MODULE_NAMES = vars(types.ModuleType)["__dict__"]


def file_of(module: object) -> object:
    """The file an entry of ``sys.modules`` names in its namespace, read by its type alone, so
    that no attribute hook of a lazy module runs; None for an entry that is not a module."""
    if not issubclass(type(module), types.ModuleType):
        return None
    return namespace(module).get("__file__")


def namespace(value: object) -> Mapping[str, object]:
    """The names a class or a module holds in its own namespace, read through the descriptor
    ``type`` or ``types.ModuleType`` defines, so that no attribute hook of the value's own class
    runs; empty for any other value."""
    if issubclass(type(value), type):
        return _CLASS_NAMES.__get__(value)
    if issubclass(type(value), types.ModuleType):
        return _MODULE_NAMES.__get__(value)
    return {}
