"""A file of seeds, one JSON object per line: read, each line checked, and repeats left out."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.config.command_line import UsageError
from pyct.run.seed_checks import SeedCheck, parse_seed
from pyct.run.target import Target

# what JSON reads as space between values within a line: a line of only these is blank
_BLANK = " \t"
# the byte-order mark an editor may write at a file's start
_MARK = "\ufeff"


@dataclass(frozen=True)
class SeedsFile:
    """A seeds file's name as the command line gave it, and each line that is not blank, with
    its number from 1."""

    name: str
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class FileSeed:
    """One seed of a seeds file, the file's name and the seed's line."""

    seed: Mapping[str, object]
    file: str
    line: int

    @property
    def label(self) -> str:
        """Where the seed came from, as ``FILE:N``."""
        return f"{self.file}:{self.line}"


def read_seeds_file(name: str) -> SeedsFile:
    """Read the file ``name`` names. Refuse an empty name, and a file that cannot be read or
    holds only blank lines. A byte-order mark at a line's start is not part of the line.

    A line ends where Python's text reading ends one, at ``\\n``, ``\\r\\n`` or
    ``\\r``; a line separator ``splitlines`` would also split on, such as
    U+2028 inside a JSON string, stays in its line.
    """
    if not name:
        raise UsageError("--seeds needs a file name")
    try:
        text = Path(name).read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read {name}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise UsageError(f"cannot read {name}: {error}") from error
    numbered = enumerate((line.removeprefix(_MARK) for line in text.split("\n")), start=1)
    lines = tuple((number, line) for number, line in numbered if line.strip(_BLANK))
    if not lines:
        raise UsageError(f"{name} holds no seed")
    return SeedsFile(name, lines)


def checked_seeds(target: Target, file: SeedsFile) -> tuple[FileSeed, ...]:
    """Each line's seed, checked as ``--args`` checks one: its shape, its names, then its types.

    Every bad line is refused at once, each reason the checks give after a
    ``FILE:N: `` of its own; a reason that holds a line break, as a key may,
    keeps it.
    """
    check = SeedCheck.of(target)
    seeds: list[FileSeed] = []
    refusals: list[str] = []
    for number, text in file.lines:
        seed, reasons = _checked(check, text)
        refusals += [f"{file.name}:{number}: {reason}" for reason in reasons]
        if seed is not None:
            seeds.append(FileSeed(seed, file.name, number))
    if refusals:
        raise UsageError("\n".join(refusals))
    return tuple(seeds)


def _checked(check: SeedCheck, text: str) -> tuple[Mapping[str, object] | None, list[str]]:
    """The line's seed and no reason, or no seed and each reason the line is refused."""
    try:
        seed = parse_seed(text)
    except UsageError as error:
        return None, [str(error)]
    reasons = check.refusals(seed)
    return (None, reasons) if reasons else (seed, [])


def distinct(seeds: Sequence[FileSeed]) -> tuple[tuple[FileSeed, ...], tuple[str, ...]]:
    """The seeds without one an earlier line gave, and a ``skipped`` line for each left out.

    Two seeds are the same when they write the same JSON: the same keys in the
    same order, each value of the same type, so ``1`` and ``1.0`` differ and
    the spaces between them do not count.
    """
    first: dict[str, int] = {}
    kept: list[FileSeed] = []
    skipped: list[str] = []
    for each in seeds:
        written = json.dumps(each.seed)
        if written in first:
            skipped.append(f"skipped {each.label}, same seed as line {first[written]}")
        else:
            first[written] = each.line
            kept.append(each)
    return tuple(kept), tuple(skipped)
