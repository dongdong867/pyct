"""Legacy results kept between runs: legacy is ``main``, so its side of a row repeats.

A kept result is reused while nothing it depends on has changed. Its key holds two parts:

- the run's context, one for every row: legacy's checkout path, its commit and the changes to
  its tracked files, legacy's Python release, the cvc5 version, the distributions legacy's
  environment has installed, and the contents of the checker files that run and read the
  legacy side;
- the row's own: its target, seed, limits as legacy is given them, how long the side may run,
  the library an installed entry names, and the sources of the target under its root.

The sources are the target module's file, its packages' ``__init__.py`` files, and every
module under the root that an ``import`` statement in one of them names, followed through
those modules in turn. An installed entry's module sits in legacy's environment, not under its
root, so its installed distributions stand for its sources, and the checkout's path is in the
context, since the report names files there. A run whose commit, changes, Python or cvc5
version cannot be read has no context, and nothing of its is kept.

Each result is one JSON file, ``legacy/KEY.json`` in the cache folder, written whole before it
is renamed into place, so rows that run at once never read half of one. Its paths under the
row's root are read back under the root of the run that reads it, so checkouts at other paths
share results. A result whose legacy side spent its budget is kept too; ``refresh_budget_spent``
runs such a row's legacy side again and keeps the new result.
"""

import ast
import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from tools.compare_coverage.sides import (
    Installed,
    SideReport,
    SideRequest,
    installed_of,
    lines_of,
    optional_count,
    optional_text,
)

# the shape of a kept result; a new shape keys every result anew
FORMAT = 1

# the variable that names the cache folder, before the user's cache folder
FOLDER_VARIABLE = "PYCT_COMPARE_CACHE"

# legacy's stop for a run that spent its budget
BUDGET_SPENT = "timeout"

# the checker's files that run the legacy side and read what it says
CHECKER_FILES = (
    "legacy_adapter.py",
    "legacy_side.py",
    "library_probe.py",
    "process.py",
    "sides.py",
)

HERE = Path(__file__).parent

LOGGER = logging.getLogger(__name__)


def default_folder(environ: Mapping[str, str], home: Path) -> Path:
    """``$PYCT_COMPARE_CACHE``, else ``pyct/compare-coverage`` in the user's cache folder."""
    named = environ.get(FOLDER_VARIABLE)
    if named:
        return Path(named)
    user = environ.get("XDG_CACHE_HOME") or str(home / ".cache")
    return Path(user) / "pyct" / "compare-coverage"


@dataclass(frozen=True)
class Legacy:
    """What every legacy result of one run depends on, ``None`` where it could not be read.

    ``checkout`` is the checkout's path: an installed entry's report names files in its
    environment. ``changes`` is the hash of the changes to its tracked files, ``installed``
    its environment's ``NAME-VERSION.dist-info`` folders.
    """

    checkout: Path
    commit: str | None
    changes: str | None
    python: str | None
    cvc5: str | None
    installed: tuple[str, ...]


def run_context(legacy: Legacy) -> str | None:
    """The part of every key one run shares, or ``None`` when a fact of it is not known."""
    known = (legacy.commit, legacy.changes, legacy.python, legacy.cvc5)
    if any(fact is None for fact in known):
        return None
    checker = {name: _digest((HERE / name).read_bytes()) for name in CHECKER_FILES}
    facts = {
        "format": FORMAT,
        "checkout": str(legacy.checkout.resolve()),
        "commit": legacy.commit,
        "changes": legacy.changes,
        "python": legacy.python,
        "cvc5": legacy.cvc5,
        "installed": list(legacy.installed),
        "checker": checker,
    }
    return _digest(_canonical(facts))


def clear(folder: Path) -> int:
    """Remove every kept result in ``folder`` and give how many there were."""
    kept = list(_kept(folder))
    for file in kept:
        file.unlink(missing_ok=True)
    return len(kept)


def _kept(folder: Path) -> Iterator[Path]:
    """Every kept result, and every part of one a failed write left."""
    results = folder / "legacy"
    if not results.is_dir():
        return iter(())
    return (file for file in results.iterdir() if file.suffix in (".json", ".part"))


@dataclass(frozen=True)
class Cache:
    """Where results are kept, the run's context, and whether budget-spent ones run again."""

    folder: Path
    context: str
    refresh_budget_spent: bool = False

    def key(self, request: SideRequest, limits: Mapping[str, float]) -> str:
        """The key of the request's legacy result under limits as legacy is given them."""
        module = request.target.split("::")[0]
        row = {
            "context": self.context,
            "target": request.target,
            "seed": request.seed,
            "limits": dict(limits),
            "wait": request.wait,
            "library": request.library,
            "sources": {} if request.library else sources(module, request.root),
        }
        return _digest(_canonical(row))

    def get(self, key: str, root: Path) -> SideReport | None:
        """The result kept under ``key``, marked reused, or ``None`` when there is none to use."""
        try:
            kept = json.loads((self.folder / "legacy" / f"{key}.json").read_text("utf-8"))
            report = _report(kept["report"], kept["root"], root)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        if self.refresh_budget_spent and report.stopped == BUDGET_SPENT:
            return None
        return report

    def put(self, key: str, report: SideReport, root: Path) -> None:
        """Keep ``report`` under ``key``, replacing whole any result kept there before.

        A result that cannot be written is not kept, and the row goes on: the next run runs
        its legacy side again.
        """
        folder = self.folder / "legacy"
        text = json.dumps({"root": str(root), "report": _fields(report)})
        part = None
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", dir=folder, suffix=".part", delete=False) as file:
                part = Path(file.name)
                file.write(text)
            os.replace(part, folder / f"{key}.json")
        except OSError as error:
            LOGGER.warning("cannot keep a legacy result in %s: %s", folder, error)
            if part is not None:
                part.unlink(missing_ok=True)


def _fields(report: SideReport) -> dict[str, object]:
    library = report.library
    return {
        "file": report.file,
        "covered": sorted(report.covered),
        "stopped": report.stopped,
        "inputs": report.inputs,
        "failure": report.failure,
        "library": None if library is None else _library(library),
    }


def _library(library: Installed) -> dict[str, object]:
    return {"version": library.version, "root": library.root, "provides": library.provides}


def _report(fields: dict[str, object], kept_root: object, root: Path) -> SideReport:
    """The kept fields as a reused report, their paths under the kept root moved to ``root``."""
    if not isinstance(kept_root, str):
        raise ValueError(f"a kept root is a path, got {kept_root!r}")
    return SideReport(
        file=_moved(optional_text(fields["file"]), kept_root, root),
        covered=lines_of(fields["covered"]),
        stopped=optional_text(fields["stopped"]),
        inputs=optional_count(fields["inputs"]),
        failure=_moved(optional_text(fields["failure"]), kept_root, root),
        library=installed_of(fields["library"]),
        reused=True,
    )


def _moved(text: str | None, kept_root: str, root: Path) -> str | None:
    """``text`` with each path under ``kept_root`` written under ``root`` instead."""
    if text is None or kept_root == str(root):
        return text
    return text.replace(kept_root + os.sep, str(root) + os.sep)


def sources(module: str, root: Path) -> dict[str, str]:
    """Each file under ``root`` an import statement reached from ``module`` names, with its
    contents' hash.

    The module docstring says which files these are. Paths are relative to ``root``.
    """
    found: dict[str, str] = {}
    waiting = [*_packages(module), module]
    seen: set[str] = set()
    while waiting:
        name = waiting.pop()
        if name in seen:
            continue
        seen.add(name)
        file = _module_file(name, root)
        if file is None:
            continue
        data = file.read_bytes()
        found[file.relative_to(root).as_posix()] = _digest(data)
        waiting += _imported(data, name, file.name == "__init__.py")
    return found


def _module_file(name: str, root: Path) -> Path | None:
    """The file that holds module ``name`` under ``root``: a package's, else a module's."""
    path = root.joinpath(*name.split("."))
    for file in (path / "__init__.py", path.with_suffix(".py")):
        if file.is_file():
            return file
    return None


def _imported(data: bytes, name: str, package: bool) -> list[str]:
    """Every module an import statement in module ``name``'s source names, with its packages.

    ``from A import B`` names ``A`` and ``A.B``, since ``B`` can be a module of package ``A``.
    """
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError):
        return []
    here = name if package else name.rpartition(".")[0]
    named: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            named += _from(node, here)
    return [module for name in named for module in (*_packages(name), name)]


def _from(node: ast.ImportFrom, here: str) -> list[str]:
    """The modules ``from ... import ...`` names, its dots read from package ``here``."""
    base = node.module or ""
    if node.level:
        # each dot past the first climbs one package; none can climb past the top one
        parts = here.split(".") if here else []
        if node.level > len(parts):
            return []
        start = ".".join(parts[: len(parts) - node.level + 1])
        base = f"{start}.{base}" if base else start
    return [base, *(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")]


def _packages(name: str) -> list[str]:
    """The packages that hold module ``name``: ``a`` and ``a.b`` for ``a.b.c``."""
    parts = name.split(".")
    return [".".join(parts[:end]) for end in range(1, len(parts))]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
