"""pyct's own imports, once a target's folder is on the import path: from the standard library.

``load_target`` puts the target's folder first on the import path, as plain
Python puts the folder of the script it runs. From then on, a module pyct's
code imports for the first time would come from that folder when the
folder holds one of the same name, and so would a module a function of the
standard library imports when pyct's code calls it: on Python 3.14,
``traceback`` imports ``difflib`` as pyct reads a SyntaxError's message.

So ``load_target`` also puts a finder just ahead of Python's path finder.
For a top-level module Python has not imported yet, it reads the frames
the import runs under, from the import outward, past the standard
library's own and past those of pyct's core, which runs the target's own
operations in its place: a substituted operation, a tracked value's
method, a bound builtin. When the first frame past them is pyct's, the
import is pyct's own, and the finder looks for the module in the standard
library's entries of the import path alone; one it does not find there,
the path finder looks for on the whole path, as always. Any other import
is the path finder's alone: that of the target's code, and of code it
calls or pyct's core runs for it, whoever called the target, when that
code lies outside the standard library. So the target imports from its
folder as it would under plain Python. So is a module of a loaded
target's top-level package, which pyct imports for the target. A target
whose own code lies in the standard library, which pyct calls with none
of the target's frames between, has its imports taken as pyct's.

The finder stays for the rest of the process. Only an import the frames
make pyct's own changes where it looks, and that module then comes from
the standard library, as it does before any folder joins the path.
"""

from __future__ import annotations

import functools
import importlib.machinery
import os
import sys
import types
from collections.abc import Sequence

from pyct.core.branch import PYCT_DIR

# the folder of pyct's core, whose code runs the target's own operations in its place
_CORE = f"{PYCT_DIR}core{os.sep}"


def _installed_folders() -> tuple[str, ...]:
    """The folders ``site`` looks in for installed packages, each with a separator on its end.

    One can lie inside the standard library's folder, as a system Python's
    own site-packages does. They are read from ``site`` itself, which
    imports nothing to answer; none when Python started without ``site``,
    as ``-S`` has it, which then puts none of them on the path. Each is
    named as its links lead.
    """
    site = sys.modules.get("site")
    if site is None:
        return ()
    folders = [*site.getsitepackages(), site.getusersitepackages()]
    return tuple(f"{os.path.realpath(folder)}{os.sep}" for folder in folders)


# the folder the standard library's own files lie in, lib-dynload's included, as its links lead,
# with a separator on its end; read from os, which every interpreter has imported, so reading it
# imports nothing
_STANDARD = f"{os.path.realpath(os.path.dirname(os.__file__))}{os.sep}"
_INSTALLED = _installed_folders()
# how the file name of code frozen into the interpreter starts, the import system's included
_FROZEN = "<frozen "


class _OwnImports:
    """Finds pyct's own imports in the standard library, and leaves every other one alone.

    ``targets`` holds the top-level packages of the targets loaded in this
    process: pyct imports their modules for the target, never for itself.
    """

    def __init__(self) -> None:
        self.targets: set[str] = set()

    def find_spec(
        self,
        name: str,
        path: Sequence[str] | None = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        # a submodule is looked for in its package's folders, which its package's import chose
        if path is not None or name in self.targets:
            return None
        if not _pyct_s(sys._getframe(1)):
            return None
        return importlib.machinery.PathFinder.find_spec(name, _standard_entries())


def keep_own_imports(package: str) -> None:
    """From now on, look for pyct's own imports in the standard library, and leave the modules
    of the top-level package ``package`` to the target.

    The finders become a new list, so another thread's import that walks
    the old one does not see it shift. With no path finder among them, as a
    host can leave it, the finder goes last.
    """
    own = next((finder for finder in sys.meta_path if isinstance(finder, _OwnImports)), None)
    if own is None:
        own = _OwnImports()
        finders = list(sys.meta_path)
        path_finder = importlib.machinery.PathFinder
        at = finders.index(path_finder) if path_finder in finders else len(finders)
        sys.meta_path = [*finders[:at], own, *finders[at:]]
    own.targets.add(package)


def _pyct_s(frame: types.FrameType | None) -> bool:
    """Whether the first frame from ``frame`` outward that is neither the standard library's
    nor pyct's core's is pyct's."""
    while frame is not None:
        file = frame.f_code.co_filename
        if not (file.startswith(_CORE) or _standard(file)):
            return file.startswith(PYCT_DIR)
        frame = frame.f_back
    return False


@functools.cache
def _standard(path: str) -> bool:
    """Whether the file or folder is the standard library's, as its links lead.

    Code frozen into the interpreter is; any other name in angle brackets,
    such as ``<string>``, names no file and is not.
    """
    if path.startswith("<"):
        return path.startswith(_FROZEN)
    resolved = f"{os.path.realpath(path)}{os.sep}"
    return resolved.startswith(_STANDARD) and not resolved.startswith(_INSTALLED)


def _standard_entries() -> list[str]:
    """The entries of the import path that hold the standard library, in their order."""
    return [entry for entry in sys.path if isinstance(entry, str) and _standard(entry)]
