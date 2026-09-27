"""The import hook: the target's package loads with its compares substituted.

The owner of a run opens `intercepting` before the target's import and
keeps it open until the run ends: ``pyct run`` in its own process, and each
fresh interpreter around its one input. While it is open, a finder at the
front of ``sys.meta_path`` claims every module of the target's top-level
package that Python would load from a ``.py`` file, whenever it is first
imported, a module first imported during a call included. A forked input
inherits the open block with the process.

Nothing is set aside or put back: each module is imported once per
process. A module of the package imported before the block opened stays as
Python loaded it.

The loader is Python's own source loader but for two steps. It binds the
names substituted code calls in each module before the module's code runs,
``__pyct_in__`` and the rest, and it takes
the module's code from `pyct.intercept.cache`, substituted, never from
``__pycache__``, which it neither reads nor writes. The module's code runs
as Python runs it, so a raise at import has no pyct frame under it, and
``inspect.getsource``, tracebacks and package data read the file as written.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import sys
import types
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.core import substitutes
from pyct.core.values import own
from pyct.intercept.cache import cached
from pyct.intercept.compiled import substituted_code
from pyct.intercept.substitute import BOUND


@dataclass(frozen=True)
class Interception:
    """What one block substitutes: the target's module, whose top-level package is in scope, and
    the folder its substituted code is kept in.

    For ``shop.cart`` the scope is ``shop`` and every module under it; for a
    top-level module, that module alone.
    """

    module: str
    cache: Path

    @property
    def package(self) -> str:
        return self.module.partition(".")[0]

    def holds(self, name: str) -> bool:
        """Whether the module of this name is in scope."""
        return name == self.package or name.startswith(f"{self.package}.")


def prepare(namespace: dict[str, object]) -> None:
    """Bind in a module's namespace the names its substituted code calls.

    Each name is a dunder, so ``from m import *`` does not hand it on. The
    loader prepares each module it creates, before the module's code runs.
    """
    for name, function in BOUND.items():
        namespace[name] = getattr(substitutes, function)


@contextlib.contextmanager
def intercepting(interception: Interception) -> Iterator[None]:
    """Substitute the modules in scope as Python imports them, until the block ends."""
    finder = _Finder(interception)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path[:] = [each for each in sys.meta_path if each is not finder]


def current() -> Interception | None:
    """The interception of the block open in this process, or None when none is open."""
    finders = [each for each in sys.meta_path if isinstance(each, _Finder)]
    return finders[0].interception if finders else None


class _Finder:
    """Claims each module in scope that Python would load from its source file.

    It asks the finders behind it, in their order, as Python would, and
    swaps its own loader into the spec the first one finds. Asking all of
    them, not only the path finder, keeps a package an editable install
    serves through its own finder. Any other spec, an extension module, a
    namespace package or bytecode without a source, goes back as it came.
    """

    def __init__(self, interception: Interception) -> None:
        self.interception = interception

    def find_spec(
        self,
        name: str,
        path: Sequence[str] | None = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not self.interception.holds(name):
            return None
        spec = self._found(name, path, target)
        if spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader:
            return spec
        spec.loader = _Loader(name, spec.loader.path, self.interception.cache)
        return spec

    def _found(
        self, name: str, path: Sequence[str] | None, target: types.ModuleType | None
    ) -> importlib.machinery.ModuleSpec | None:
        for finder in sys.meta_path:
            find = getattr(finder, "find_spec", None)
            if finder is self or find is None:
                continue
            spec = find(name, path, target)
            if spec is not None:
                return spec
        return None


class _Loader(importlib.machinery.SourceFileLoader):
    """Python's source loader, with the module's code substituted and kept in pyct's cache."""

    def __init__(self, fullname: str, path: str, cache: Path) -> None:
        super().__init__(fullname, path)
        self.cache = cache

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> types.ModuleType:
        """The module, prepared before any of its code runs."""
        module = types.ModuleType(spec.name)
        prepare(vars(module))
        return module

    def get_code(self, fullname: str) -> types.CodeType:
        """The module's code, substituted, for the source file as it is now.

        Reading the file is pyct's work for the target, so a raise out of it
        is the target's, as it is in Python's own import.
        """
        path = self.get_filename(fullname)
        return cached(
            self.cache,
            path,
            lambda: own(self.get_data, path),
            lambda source: substituted_code(source, path),
        )
