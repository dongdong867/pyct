"""Whether a class is the user's own or a library's: Python's standard library's, or an installed
distribution's other than the package of the code whose hint names it. A hint builds only the
user's own classes (``hints``). A module is told from its name alone (``library_module``), with
no package excepted, so a class an LLM seed names is refused before its module is imported."""

from __future__ import annotations

import functools
import importlib.util
import os
import sys

# where the standard library's and installed distributions' code lives, each folder both as the
# path spells it and as its links lead, with a separator on its end. Read off `os`'s file and the
# path rather than `sysconfig`, which a target may ship a module of its own as
LIBRARY_ROOTS = tuple(
    dict.fromkeys(
        os.path.join(spelled, "")
        for path in (
            os.path.dirname(os.__file__),
            *(
                entry
                for entry in sys.path
                if os.path.basename(entry) in ("site-packages", "dist-packages")
            ),
        )
        for spelled in (path, os.path.realpath(path))
    )
)


def from_a_library(cls: type, owner: object = None) -> bool:
    """Whether ``cls`` comes from a library, for a hint written on ``owner``.

    A class of the same package as ``owner``'s module is never a library's,
    so a target inside an installed library builds the classes of its own
    regular package, the nearest one with an ``__init__.py``. A package
    here is the shortest dotted prefix of the module's name whose module
    has a file (``package_of``), so the portions of a namespace package,
    each its own distribution, are packages of their own, and a module
    placed directly in a namespace package is a package of its own too. Any
    other class is a library's when its module's file, as written or as its
    links lead, lies under Python's standard library or a folder of
    installed distributions on the path (``LIBRARY_ROOTS``), or, for a
    module with no file, when its top-level name is a standard library
    module's (``sys.stdlib_module_names``), ``builtins`` among them. A class
    whose module is not loaded is read by that name alone.
    """
    name = cls.__module__ if isinstance(cls.__module__, str) else ""
    owned = getattr(owner, "__module__", None)
    if name and isinstance(owned, str) and package_of(name) == package_of(owned):
        return False
    return _library_module(name)


def library_module(name: str) -> bool:
    """Whether the module ``name`` is a library's. It imports nothing: it reads a loaded
    module's ``__file__`` or ``__spec__``, or a loaded top-level module's ``__spec__``, or asks
    ``importlib.util.find_spec`` for the top-level name, which runs the import path's finders.

    A loaded module with a file is a library's when the file, as written or
    as its links lead, lies under ``LIBRARY_ROOTS``. Any other module is a
    library's when its top-level name is a standard library module's, or by
    its spec: a loaded module's own, else its top-level name's. The spec is
    a library's when its file, or else every folder it spans, lies under
    ``LIBRARY_ROOTS``, or when it has neither a file nor a folder, as a
    frozen or built-in module's spec has. So a namespace package is told
    the same before and after it is imported. No package is excepted, as a
    hint's owner's is in ``from_a_library``.
    """
    module = sys.modules.get(name)
    if module is not None and isinstance(getattr(module, "__file__", None), str):
        return _library_module(name)
    top = name.partition(".")[0]
    if top in sys.stdlib_module_names:
        return True
    if module is not None:
        spec = getattr(module, "__spec__", None)
    else:
        loaded = sys.modules.get(top)
        spec = (
            importlib.util.find_spec(top) if loaded is None else getattr(loaded, "__spec__", None)
        )
    if spec is None:
        return False
    places = [spec.origin] if spec.has_location and spec.origin else spec.submodule_search_locations
    found = list(places or ())
    return not found or all(_under_roots(place) for place in found)


def package_of(name: str) -> str:
    """The package a module belongs to: the shortest dotted prefix of its name whose module has
    a file, which a namespace package has none of, or the whole name when none has one. So a
    module placed directly in a namespace package, as ``google/cloud/*.py``, is a package of
    its own, apart from its sibling modules."""
    parts = name.split(".")
    for end in range(1, len(parts)):
        prefix = ".".join(parts[:end])
        if isinstance(getattr(sys.modules.get(prefix), "__file__", None), str):
            return prefix
    return name


@functools.cache
def _library_module(name: str) -> bool:
    """Whether the module ``name`` is a library's, read once per name."""
    file = getattr(sys.modules.get(name), "__file__", None)
    if not isinstance(file, str):
        return name.partition(".")[0] in sys.stdlib_module_names
    return _under_roots(file)


def _under_roots(path: str) -> bool:
    """Whether ``path``, as written or as its links lead, lies under ``LIBRARY_ROOTS``."""
    return path.startswith(LIBRARY_ROOTS) or os.path.realpath(path).startswith(LIBRARY_ROOTS)
