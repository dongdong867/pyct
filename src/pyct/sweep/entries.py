"""The entries one swept module holds, each named by the module whose file holds its code.

``pyct run`` counts the lines of the module it names, so an entry is named
by the module whose file holds its code, under a name that module gives it
(sweep-names-an-entry-by-the-file-that-holds-its-code). A function that
``dateutil/parser/__init__.py`` re-exports from ``._parser`` is
``dateutil.parser._parser::parse``, and a function several modules export is
one entry.

A public name is one in ``__all__``, or, with no ``__all__``, one without a
leading underscore. It holds an entry when it holds a function, looked at
through ``__wrapped__``, or a class, whose code is in a ``.py`` file of a
module of the swept package. A class is an entry when its constructor is
Python code, since ``pyct run MODULE::Class`` calls it. Each method a class's
own body defines under a public name is listed too, and skipped until
``pyct run`` can call one.
"""

import functools
import inspect
import os
import pkgutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import FunctionType, ModuleType

from pyct.sweep.seeds import NoSeedError, seed_of

METHOD = "pyct run cannot call a method yet"
GENERATED = "generated code"

# the attributes whose Python code makes a class's constructor Python code
CONSTRUCTORS = ("__init__", "__new__")


@dataclass(frozen=True)
class Entry:
    """One entry: its module and name, and its seed, or the reason it is skipped."""

    module: str
    name: str
    seed: Mapping[str, object] | None = None
    skip: str | None = None


@dataclass(frozen=True)
class Unread:
    """What raised while a module was read: the public name, or None for the module's names
    as a whole, and Python's words for the error, its repr."""

    name: str | None
    error: str


@dataclass(frozen=True)
class Reading:
    """What reading one module found: its entries, and the first read that raised."""

    entries: list[Entry]
    unread: Unread | None = None


def entries_in(module: ModuleType, found_in: str, package: str) -> Reading:
    """Every entry the public names of ``module``, the module ``found_in`` of ``package``, hold.

    Reading a name can run the module's code, a lazy attribute or a
    ``__class__`` property, and raise though the import did not. Such a name
    holds no entry, and the first one is kept, with Python's own words, so
    the module's row can say which name and why. A package's ``__all__`` may
    name a module below it that the package does not import, as
    ``from package import *`` would import it; that name is no error, since
    the walk lists the module on its own. The module is named as the walk
    reached it, since an object a module put in its own place may have no
    ``__name__``.
    """
    found = _Package(package)
    entries: list[Entry] = []
    unread: Unread | None = None
    for name in public_names(module):
        try:
            entries.extend(found.entries(module, found_in, name))
        except Exception as error:
            if name not in _modules_below(module):
                unread = unread or Unread(name, repr(error))
    return Reading(entries, unread)


def package_path(module: ModuleType) -> list[str] | None:
    """The folders a package's modules are in, or None for a plain module.

    Read from the module's own names, not by asking it: a module-level
    ``__getattr__`` that raises for any name it lacks would run and raise.
    """
    try:
        path = vars(module).get("__path__")
    except TypeError:
        return None
    return None if path is None else list(path)


def _modules_below(module: ModuleType) -> set[str]:
    """The names of the modules one level below a package, or none for a plain module."""
    path = package_path(module)
    return set() if path is None else {found.name for found in pkgutil.iter_modules(path)}


def public_names(module: ModuleType) -> list[str]:
    """The names in ``__all__`` when the module defines it, else every name without ``_``."""
    listed = getattr(module, "__all__", None)
    if isinstance(listed, list | tuple):
        return [name for name in listed if isinstance(name, str)]
    return [name for name in vars(module) if not name.startswith("_")]


class _Package:
    """The swept package as its modules stand now: which file is which module's, and which
    names each module gives the functions and classes it holds."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.files = _files(name)
        self.module_count = len(sys.modules)
        self.holders: dict[str, dict[int, list[str]]] = {}

    def entries(self, module: ModuleType, found_in: str, name: str) -> list[Entry]:
        """The entries the public name ``name`` of ``module`` holds: none, one, or a class's."""
        value = getattr(module, name)
        if isinstance(value, type):
            return self._class_entries(value, found_in, name)
        target = function_of(value)
        if target is None:
            return []
        return self._function_entries(target, found_in, name)

    def _function_entries(self, target: object, found_in: str, found_as: str) -> list[Entry]:
        file = _code_file(target)
        if file is None:
            owner = getattr(target, "__module__", None)
            generated = isinstance(owner, str) and _within(owner, self.name)
            return [Entry(found_in, found_as, skip=GENERATED)] if generated else []
        home = self._home_of(file)
        if home is None:
            return []
        name = self._name_in(home, target)
        if name is None:
            return [_unnamed(home, found_in, found_as)]
        return [seeded(home, name, vars(sys.modules[home])[name])]

    def _class_entries(self, cls: type, found_in: str, found_as: str) -> list[Entry]:
        home = self._class_home(cls)
        constructed = _python_constructor(cls)
        methods = own_methods(cls)
        if home is None or not (constructed or methods):
            return []
        name = self._name_in(home, cls)
        if name is None:
            return [_unnamed(home, found_in, found_as)]
        rows = [Entry(home, f"{name}.{method}", skip=METHOD) for method in methods]
        return [seeded(home, name, cls), *rows] if constructed else rows

    def _class_home(self, cls: type) -> str | None:
        """The module of the package whose file holds the class's code, or None.

        A function the class body compiled says where the body is: its
        compiled qualified name starts with the class's, a property's accessors
        and a ``cached_property``'s function included. The ``_make`` a named
        tuple takes from Python claims the class's ``__qualname__`` but was
        compiled elsewhere, so it says nothing. A function borrowed from a
        same-named class elsewhere does match, so the first matching function
        in the package decides, and a class whose matching functions are all
        outside the package has no home, whatever ``__module__`` says; a library
        may rewrite that. Only a class whose body compiled no function falls
        back to the module ``__module__`` names.
        """
        prefix = f"{cls.__qualname__}."
        matched = False
        for target in [part for value in list(vars(cls).values()) for part in _compiled(value)]:
            if target.__code__.co_qualname.startswith(prefix):
                matched = True
                home = self._home_of(_code_file(target))
                if home is not None:
                    return home
        if matched:
            return None
        return self._home_of(getattr(sys.modules.get(cls.__module__), "__file__", None))

    def _home_of(self, file: object) -> str | None:
        """The module of the package whose file ``file`` is, or None.

        Reading a name can import a module, as a module's ``__getattr__`` that
        loads its API on first use does, so the files are read again when the
        count of imported modules has changed since they were last read.
        """
        if not isinstance(file, str):
            return None
        if len(sys.modules) != self.module_count:
            self.files = _files(self.name)
            self.module_count = len(sys.modules)
        return self.files.get(os.path.realpath(file))

    def _name_in(self, home: str, target: object) -> str | None:
        """The name ``home`` gives ``target``: its own name when that holds it, else the first."""
        if home not in self.holders:
            self.holders[home] = _holders(sys.modules[home])
        names = self.holders[home].get(id(target), [])
        own = getattr(target, "__name__", None)
        if own in names:
            return own
        return min(names, default=None)


def _unnamed(home: str, found_in: str, found_as: str) -> Entry:
    """Code whose home module holds it under no name, as a factory's function: skipped, named
    where it was found."""
    return Entry(found_in, found_as, skip=f"no name in {home} holds it")


def seeded(module: str, name: str, value: Callable[..., object]) -> Entry:
    """The entry with the seed sweep gives ``value``, or skipped with the reason it has none."""
    try:
        return Entry(module, name, seed=seed_of(value))
    except NoSeedError as error:
        return Entry(module, name, skip=str(error))


def function_of(value: object) -> object | None:
    """The Python function ``value`` is, or wraps through ``__wrapped__``, or None.

    A staticmethod or classmethod is read at its function. ``inspect.unwrap``
    raises on a wrapper loop, which is no function either.
    """
    if isinstance(value, staticmethod | classmethod):
        value = value.__func__
    if not callable(value):
        return None
    try:
        target = inspect.unwrap(value)
    except Exception:
        return None
    return target if inspect.isfunction(target) else None


def _compiled(value: object) -> list[FunctionType]:
    """The Python functions a value in a class body holds: the value itself, a property's
    getter, setter and deleter, or a ``cached_property``'s function."""
    parts: list[object] = [value]
    if isinstance(value, property):
        parts = [value.fget, value.fset, value.fdel]
    elif isinstance(value, functools.cached_property):
        parts = [value.func]
    found = [function_of(part) for part in parts]
    return [target for target in found if isinstance(target, FunctionType)]


def own_methods(cls: type) -> list[str]:
    """The public names the class's own body gives a function, static and class methods too."""
    return [
        name
        for name, value in vars(cls).items()
        if not name.startswith("_") and function_of(value) is not None
    ]


def _python_constructor(cls: type) -> bool:
    """Whether the ``__init__`` or ``__new__`` the class takes is Python code, generated or not."""
    return any(function_of(getattr(cls, name, None)) is not None for name in CONSTRUCTORS)


def _code_file(target: object) -> str | None:
    """The source file a function's code was compiled from, or None when there is none."""
    code = getattr(target, "__code__", None)
    file = getattr(code, "co_filename", None)
    return file if isinstance(file, str) and os.path.isfile(file) else None


def _files(package: str) -> dict[str, str]:
    """Each ``.py`` file of an imported module of ``package``, by real path, to its module.

    Modules are read in name order, so a file two names import is the first name's.
    """
    files: dict[str, str] = {}
    for name, module in sorted(list(sys.modules.items()), key=lambda item: item[0]):
        # a module outside the package is never asked anything: a lazy one would load
        if not _within(name, package):
            continue
        file = _attribute(module, "__file__")
        if isinstance(file, str) and file.endswith(".py"):
            files.setdefault(os.path.realpath(file), name)
    return files


def _holders(module: ModuleType) -> dict[int, list[str]]:
    """The names ``module`` gives each class and each function, by the object's identity."""
    held: dict[int, list[str]] = {}
    for name, value in list(vars(module).items()):
        target = _held(value)
        if target is not None:
            held.setdefault(id(target), []).append(name)
    return held


def _held(value: object) -> object | None:
    """The class or function ``value`` is, or None when asking raises: a value that cannot be
    read names no entry, and a public one says so where its own module is read."""
    try:
        return value if isinstance(value, type) else function_of(value)
    except Exception:
        return None


def _attribute(holder: object, name: str) -> object | None:
    """``holder``'s attribute ``name``, or None when it has none or reading it raises."""
    try:
        return getattr(holder, name, None)
    except Exception:
        return None


def _within(name: str, package: str) -> bool:
    return name == package or name.startswith(f"{package}.")
