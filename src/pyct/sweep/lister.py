"""``python -m pyct.sweep.lister PACKAGE [--after MODULE]``: import each module of a package
and write down the entries it holds.

Sweep never imports a swept module in its own process: a module can raise,
exit, crash, or hang while it is imported, and that must cost its own row,
never the sweep (sweep-runs-each-entry-as-pyct-run). So this process imports
them, each once, and sweep reads what it writes. When a module ends this
process or stalls it, sweep starts a new one with ``--after`` that module,
which walks on past it and never imports it again.

It walks PACKAGE and, below it, every module whose name has no part that
starts with ``_`` and no part named ``test`` or ``tests``, in name order.
PACKAGE itself is walked whatever its name. A package that does not import
is not walked below. With ``--after``, a module up to that one was listed
by an earlier process: a package on the way to it is imported again to
reach the modules after it, and nothing else up to it is imported at all.

Each fact is one JSON line on the descriptor that was stdout when the
process started:

- ``{"importing": M}`` before each import, so a death or a stall is known
  to be M's;
- ``{"failed": M, "reason": R}`` for an import that raised, ``SystemExit``
  included, ``R`` its repr;
- ``{"entry": {"module", "name", "seed", "skip"}}`` for each entry M holds;
- ``{"done": true}`` at the end.

stdout is pointed at stderr before any import, so a module that prints
cannot break a line.
"""

import argparse
import importlib
import json
import os
import pkgutil
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from types import ModuleType
from typing import TextIO

from pyct.sweep.entries import entries_in

# parts of a module name below the package that leave the module out of the walk
LEFT_OUT = frozenset({"test", "tests"})


@dataclass(frozen=True)
class Walk:
    """One lister's walk: the package, the module the last lister got to, and where to write."""

    package: str
    after: str | None
    out: TextIO


def main(argv: Sequence[str] | None = None) -> int:
    """Walk the package and write each fact. Returns 0; a module's import may end it sooner."""
    parser = argparse.ArgumentParser(prog="python -m pyct.sweep.lister")
    parser.add_argument("package")
    parser.add_argument("--after")
    arguments = parser.parse_args(argv)
    walk = Walk(arguments.package, arguments.after, _facts_out())
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    _walk(walk.package, walk)
    _write(walk.out, {"done": True})
    return 0


def _facts_out() -> TextIO:
    """The descriptor stdout had, kept for the facts, with stdout itself pointed at stderr."""
    facts = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return os.fdopen(facts, "w", encoding="utf-8")


def _walk(name: str, walk: Walk) -> None:
    """Import the module ``name``, write its entries, and walk the modules below it."""
    after = walk.after
    if after is not None and name <= after and not after.startswith(f"{name}."):
        return
    module = _imported(name, walk.out)
    if module is None:
        return
    if after is None or name > after:
        for entry in entries_in(module, walk.package):
            _write(walk.out, {"entry": asdict(entry)})
    for below in _modules_below(module):
        _walk(below, walk)


def _imported(name: str, out: TextIO) -> ModuleType | None:
    """The module, imported, or None when its import raised, which is written down."""
    _write(out, {"importing": name})
    try:
        return importlib.import_module(name)
    except (Exception, SystemExit) as error:
        _write(out, {"failed": name, "reason": repr(error)})
        return None


def _modules_below(module: ModuleType) -> list[str]:
    """The modules one level below a package that the walk takes, in name order."""
    path = getattr(module, "__path__", None)
    if path is None:
        return []
    names = sorted(found.name for found in pkgutil.iter_modules(path, f"{module.__name__}."))
    return [name for name in names if _walked(name.rpartition(".")[2])]


def _walked(part: str) -> bool:
    return not part.startswith("_") and part not in LEFT_OUT


def _write(out: TextIO, fact: dict[str, object]) -> None:
    """One fact, one line, sent at once, so a process that ends next has already said it."""
    out.write(f"{json.dumps(fact)}\n")
    out.flush()


if __name__ == "__main__":
    sys.exit(main())
