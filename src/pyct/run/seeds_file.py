"""A file of seeds, one JSON object per line: read, each line checked, and repeats left out."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyct.config.command_line import UsageError
from pyct.run.seed_checks import check_seed_fits, check_seed_types, parse_seed
from pyct.run.target import Target

# what JSON reads as space between values within a line: a line of only these is blank
_BLANK = " \t"


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
    """Read the file ``name`` names. Refuse one that cannot be read, or holds only blank lines.

    A line ends where Python's text reading ends one, at ``\\n``, ``\\r\\n`` or
    ``\\r``; a line separator ``splitlines`` would also split on, such as
    U+2028 inside a JSON string, stays in its line.
    """
    try:
        text = Path(name).read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read {name}: {error.strerror}") from error
    except UnicodeDecodeError as error:
        raise UsageError(f"cannot read {name}: {error}") from error
    numbered = enumerate(text.split("\n"), start=1)
    lines = tuple((number, line) for number, line in numbered if line.strip(_BLANK))
    if not lines:
        raise UsageError(f"{name} holds no seed")
    return SeedsFile(name, lines)


def checked_seeds(target: Target, file: SeedsFile) -> tuple[FileSeed, ...]:
    """Each line's seed, checked as ``--args`` checks one: its shape, its names, then its types.

    Every bad line is refused at once, each reason the checks give on a line
    of its own, as ``FILE:N: <reason>``.
    """
    seeds: list[FileSeed] = []
    refusals: list[str] = []
    for number, text in file.lines:
        try:
            seeds.append(FileSeed(_checked(target, text), file.name, number))
        except UsageError as error:
            refusals += [f"{file.name}:{number}: {reason}" for reason in str(error).splitlines()]
    if refusals:
        raise UsageError("\n".join(refusals))
    return tuple(seeds)


def _checked(target: Target, text: str) -> Mapping[str, object]:
    seed = parse_seed(text)
    check_seed_fits(target.signature, seed)
    check_seed_types(target, seed)
    return seed


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
