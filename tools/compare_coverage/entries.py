"""The target list: which targets run, with which seed, and where each target's file lives.

``targets.json`` beside this file is one JSON document, one entry per line so a diff shows
one entry::

    {
      "sets": {"v2": {"origin": "v2", "scan": "targets"}, ...},
      "entries": [
        {"set": "v2", "target": "targets.flip.one_check::classify", "seed": {"x": 0}},
        {"set": "v2", "module": "targets.trace.broken_import", "left_out": "fails to import"},
        ...
      ]
    }

A set's ``origin`` says where its files live: ``v2`` is this checkout and ``legacy`` the
legacy checkout. ``scan``, when given, is a folder under that root whose every Python file
other than ``__init__.py`` needs an entry. An entry runs ``target``, ``MODULE::NAME``, with
``seed``, the JSON object ``pyct run --args`` takes; an entry with ``left_out`` names a module
and the reason nothing runs for it. Set, target and module names are data here, never code.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

LIST_FILE = Path(__file__).with_name("targets.json")


class ListError(Exception):
    """The target list cannot be read, or holds something that is not a set or an entry."""


class SelectionError(Exception):
    """A flag names a set or a target the list does not hold."""


class Origin(StrEnum):
    """Where a set's files live: this checkout, or the legacy checkout."""

    V2 = "v2"
    LEGACY = "legacy"


@dataclass(frozen=True)
class SetSpec:
    """A set of entries: its name, where its files live, and the folder that must be listed."""

    name: str
    origin: Origin
    scan: str | None = None


@dataclass(frozen=True)
class Entry:
    """One target to run with one seed, or one module left out with the reason."""

    set: str
    module: str
    name: str | None = None
    seed: Mapping[str, object] = field(default_factory=dict)
    left_out: str | None = None

    @property
    def target(self) -> str | None:
        """``MODULE::NAME``, or ``None`` for a left-out entry, which runs nothing."""
        return None if self.name is None else f"{self.module}::{self.name}"


@dataclass(frozen=True)
class Unlisted:
    """A file under a set's scanned folder that no entry of that set names."""

    set: str
    file: Path


@dataclass(frozen=True)
class TargetList:
    """Every set and every entry, in the order the list gives them."""

    sets: Mapping[str, SetSpec]
    entries: tuple[Entry, ...]

    def select(self, sets: Sequence[str], targets: Sequence[str]) -> tuple[Entry, ...]:
        """The entries of every named set and of every named target. With neither, all."""
        self._check(sets, targets)
        if not sets and not targets:
            return self.entries
        return tuple(
            entry for entry in self.entries if entry.set in sets or entry.target in targets
        )

    def scanned(self, sets: Sequence[str], targets: Sequence[str]) -> tuple[str, ...]:
        """The sets whose files are checked for entries: the named sets, or all with no flag."""
        if not sets and not targets:
            return tuple(self.sets)
        return tuple(name for name in self.sets if name in sets)

    def _check(self, sets: Sequence[str], targets: Sequence[str]) -> None:
        for name in sets:
            if name not in self.sets:
                known = ", ".join(self.sets)
                raise SelectionError(f"--set: no set named {name!r}; the sets are {known}")
        runnable = {entry.target for entry in self.entries}
        for target in targets:
            if target not in runnable:
                raise SelectionError(f"--target: no entry runs {target!r}")


def load_list(path: Path) -> TargetList:
    """The list in ``path``. A file that is not the list's JSON is refused, naming it."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ListError(f"cannot read the target list {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise ListError(f"the target list {path} is not JSON: {error}") from error
    return parse_list(document)


def parse_list(document: object) -> TargetList:
    """The sets and entries of a parsed list, each checked for the shape the docstring gives."""
    if not isinstance(document, dict):
        raise ListError('the target list is a JSON object with "sets" and "entries"')
    sets, entries = document.get("sets"), document.get("entries")
    if not isinstance(sets, dict) or not isinstance(entries, list):
        raise ListError('the target list is a JSON object with "sets" and "entries"')
    specs = {name: _set_spec(name, spec) for name, spec in sets.items()}
    return TargetList(
        sets=specs,
        entries=tuple(_entry(f"entry {index}", raw, specs) for index, raw in enumerate(entries, 1)),
    )


def _set_spec(name: str, spec: object) -> SetSpec:
    origins = ", ".join(Origin)
    origin = spec.get("origin") if isinstance(spec, dict) else None
    if origin not in list(Origin):
        raise ListError(f"set {name}: origin must be one of {origins}")
    scan = spec.get("scan") if isinstance(spec, dict) else None
    if scan is not None and not isinstance(scan, str):
        raise ListError(f"set {name}: scan must be a folder under the set's root")
    return SetSpec(name=name, origin=Origin(origin), scan=scan)


def _entry(where: str, raw: object, sets: Mapping[str, SetSpec]) -> Entry:
    if not isinstance(raw, dict) or not isinstance(raw.get("set"), str) or raw["set"] not in sets:
        raise ListError(f"{where}: set must name a set of the list")
    if "left_out" in raw:
        return _left_out(where, raw)
    target, seed = raw.get("target"), raw.get("seed")
    if not isinstance(target, str) or not _is_target(target):
        raise ListError(f"{where}: target must be MODULE::NAME, got {target!r}")
    if not isinstance(seed, dict):
        raise ListError(f"{where}: seed must be a JSON object, got {seed!r}")
    module, name = target.split("::")
    return Entry(set=raw["set"], module=module, name=name, seed=seed)


def _left_out(where: str, raw: dict[str, object]) -> Entry:
    module, reason = raw.get("module"), raw.get("left_out")
    if not isinstance(module, str) or not _is_module(module):
        raise ListError(f"{where}: module must be a dotted module name, got {module!r}")
    if not isinstance(reason, str) or not reason:
        raise ListError(f"{where}: left_out must give a reason")
    return Entry(set=str(raw["set"]), module=module, left_out=reason)


def _is_target(target: str) -> bool:
    module, separator, name = target.partition("::")
    return bool(separator) and _is_module(module) and name.isidentifier()


def _is_module(module: str) -> bool:
    return all(part.isidentifier() for part in module.split("."))


def entry_file(module: str, root: Path) -> Path:
    """The file ``module`` names under ``root``: ``a/b.py``, or a package's ``a/b/__init__.py``."""
    path = root.joinpath(*module.split("."))
    return path / "__init__.py" if path.is_dir() else path.with_suffix(".py")


def unlisted_files(
    target_list: TargetList, sets: Sequence[str], roots: Mapping[Origin, Path]
) -> tuple[Unlisted, ...]:
    """Every file under each named set's scanned folder that no entry of that set names."""
    found: list[Unlisted] = []
    for name in sets:
        spec = target_list.sets[name]
        if spec.scan is None:
            continue
        root = roots[spec.origin]
        listed = {entry.module for entry in target_list.entries if entry.set == name}
        for file in sorted((root / spec.scan).rglob("*.py")):
            module = ".".join(file.relative_to(root).with_suffix("").parts)
            if file.name != "__init__.py" and module not in listed:
                found.append(Unlisted(set=name, file=file))
    return tuple(found)
