"""Whether a class is the user's own or a library's: Python's standard library's, or an installed
distribution's other than the package of the code whose hint names it. A hint builds only the
user's own classes (``hints``)."""

from __future__ import annotations

import functools
import os
import site
import sys
import sysconfig


def from_a_library(cls: type, owner: object = None) -> bool:
    """Whether ``cls`` comes from a library, for a hint written on ``owner``.

    A class whose module shares its top-level package with ``owner``'s
    module is never a library's, so a target inside an installed library
    builds that library's own classes. Any other class is a library's when
    its module's file lies under Python's standard library or a folder of
    installed distributions (``site-packages``), or, for a module with no
    file, when its top-level name is a standard library module's
    (``sys.stdlib_module_names``), ``builtins`` among them. A class whose
    module is not loaded is read by that name alone.
    """
    name = cls.__module__ if isinstance(cls.__module__, str) else ""
    top = name.partition(".")[0]
    if top and top == _top_of(owner):
        return False
    return _library_module(name)


def _top_of(owner: object) -> str | None:
    """The top-level package of the module ``owner`` was written in, when it says one."""
    name = getattr(owner, "__module__", None)
    return name.partition(".")[0] if isinstance(name, str) else None


@functools.cache
def _library_module(name: str) -> bool:
    """Whether the module ``name`` is a library's, read once per name."""
    file = getattr(sys.modules.get(name), "__file__", None)
    if not isinstance(file, str):
        return name.partition(".")[0] in sys.stdlib_module_names
    path = os.path.realpath(file)
    return any(path.startswith(root + os.sep) for root in _library_roots())


@functools.cache
def _library_roots() -> tuple[str, ...]:
    """The folders Python's standard library and installed distributions live in."""
    paths = sysconfig.get_paths()
    found = [paths.get(key) for key in ("stdlib", "platstdlib", "purelib", "platlib")]
    found += [*site.getsitepackages(), site.getusersitepackages()]
    return tuple(sorted({os.path.realpath(path) for path in found if path}))
