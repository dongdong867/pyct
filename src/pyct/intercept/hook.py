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

The loader is Python's own source loader but for one step: it takes the
module's code from `pyct.intercept.cache`, substituted, never from
``__pycache__``, which it neither reads nor writes. The substituted code
imports the names it calls itself, so it runs wherever Python runs it:
imported, run by ``runpy``, or reloaded. The module's code runs as Python
runs it, so a raise at import has no pyct frame under it, and
``inspect.getsource``, tracebacks and package data read the file as written.

The positions of substituted code follow the code generator of the Python
releases the suite checked them on (`positions.CHECKED_ON`). On any other
release the block substitutes nothing and says so once, so a line table
never drifts unseen.
"""

from __future__ import annotations

import contextlib
import functools
import importlib.machinery
import logging
import sys
import types
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.core.values import own
from pyct.intercept.cache import cached
from pyct.intercept.compiled import substituted_code
from pyct.intercept.positions import CHECKED_ON

logger = logging.getLogger(__name__)


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


@contextlib.contextmanager
def intercepting(interception: Interception) -> Iterator[None]:
    """Substitute the modules in scope as Python imports them, until the block ends.

    On a Python release the suite has not checked substitution on, nothing
    is substituted, with one warning per process.
    """
    if sys.version_info[:2] not in CHECKED_ON:
        _unchecked(sys.version_info[:2])
        yield
        return
    finder = _Finder(interception)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path[:] = [each for each in sys.meta_path if each is not finder]


@functools.cache
def _unchecked(release: tuple[int, int]) -> None:
    logger.warning(
        "pyct substitutes `is True` and `in` on Python %s only; "
        "on %d.%d the target runs as written",
        ", ".join(f"{major}.{minor}" for major, minor in sorted(CHECKED_ON)),
        *release,
    )


def current() -> Interception | None:
    """The interception of the block open in this process, or None when none is open."""
    finders = [each for each in sys.meta_path if isinstance(each, _Finder)]
    return finders[0].interception if finders else None


class _Finder:
    """Claims each module in scope that Python would load from its source file.

    It asks the other finders, in their order, as Python would, and swaps
    its own loader into the spec the first one finds; another block's
    finder is never asked, so two blocks cannot ask each other forever. Asking all of
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
            # another block's finder would ask this one back, without end
            if isinstance(finder, _Finder) or find is None:
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
