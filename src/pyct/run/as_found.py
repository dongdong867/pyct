"""Work pyct does for itself as it starts, with ``sys.modules`` left as that work found it.

Some of pyct's own work imports modules a target may hold copies of, such
as the platform read's ``plistlib`` on macOS or ctypes's ``sysconfig`` on
Python 3.13 and later. Done as pyct starts, before a target's folder joins
the import path, none of them comes from that folder. Each is then dropped
again, so a target that imports one gets it from its own path, as plain
Python would, while pyct keeps what it holds of them.
"""

from __future__ import annotations

import contextlib
import sys
import threading
from collections.abc import Generator


class _Noted:
    """A finder that finds nothing, and notes each module asked for, by whether the thread that
    made it asked.

    Python asks every finder in turn for a module it has not imported yet,
    so with this one first, each module a thread imports passes it.
    """

    def __init__(self) -> None:
        self.reader = threading.get_ident()
        self.names: set[str] = set()
        self.others: set[str] = set()

    def find_spec(self, name: str, path: object = None, target: object = None) -> None:
        (self.names if threading.get_ident() == self.reader else self.others).add(name)

    def imported(self, name: str) -> bool:
        """Whether the module ``name`` is the reading thread's alone.

        It is when that thread asked for it, for a package above it, since a
        module can put another in ``sys.modules`` itself, or for a module
        under it, since a package the read imported goes with its modules;
        and no other thread asked for it, for a package above it or for a
        module under it, whose import needs its package to stay.
        """
        return _in_the_family(name, self.names) and not _in_the_family(name, self.others)


def _in_the_family(name: str, names: set[str]) -> bool:
    """Whether ``names`` holds ``name``, a package above it, or a module under it."""
    return any(
        each == name or name.startswith(f"{each}.") or each.startswith(f"{name}.") for each in names
    )


@contextlib.contextmanager
def modules_as_found() -> Generator[None]:
    """Run the block, then drop from ``sys.modules`` each module the block imported.

    So is a module put in ``sys.modules`` under one of them, as pyexpat puts
    its ``errors``. A module another thread imports meanwhile, such as a
    thread a host's ``sitecustomize`` started, stays, and so does a package
    of the block's that such a module lies under.
    """
    before = set(sys.modules)
    noted = _Noted()
    # a new list each way, never a change to this one: another thread's import may be walking it
    sys.meta_path = [noted, *sys.meta_path]
    try:
        yield
    finally:
        sys.meta_path = [finder for finder in sys.meta_path if finder is not noted]
        for name in set(sys.modules) - before:
            if noted.imported(name):
                sys.modules.pop(name, None)
