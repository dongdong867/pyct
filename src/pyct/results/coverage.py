"""Which lines a module has, which of them a run covered, and whether its branches went each way."""

from __future__ import annotations

import types
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field


def executable_lines(file: str) -> frozenset[int]:
    """Every line in the module that can fire a line event.

    Read from the compiled module's line tables, so ``def`` lines and
    module-level statements count too, though they run at import, not
    under a seed; a run counts those its import ran as covered. Line 0
    marks compiler-made instructions and is dropped.
    """
    code = compiled(file)
    lines = {line for code_object in _walk(code) for _, _, line in code_object.co_lines() if line}
    return frozenset(lines)


def compiled(file: str) -> types.CodeType:
    """The module's code, compiled from its source as the import compiles it."""
    with open(file, encoding="utf-8") as source:
        return compile(source.read(), file, "exec")


def _walk(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _walk(constant)


def no_gain(covered: Sequence[frozenset[int]], n: int) -> bool:
    """True when the last ``n`` inputs each covered no line an earlier input had.

    ``covered`` is one set per input that ran, in run order: an input that
    raised is in it; a solver miss produced no input and is not. Fewer than
    ``n`` inputs is False. A walk over the list rather than a counter kept
    beside it, so there is nothing to keep in step with the records.
    """
    if len(covered) < n:
        return False
    seen: set[int] = set()
    gains: list[bool] = []
    for lines in covered:
        gains.append(bool(lines - seen))
        seen |= lines
    return not any(gains[-n:])


@dataclass(frozen=True)
class Scope:
    """The file whose lines a run is measured against, and those lines."""

    file: str
    lines: frozenset[int]

    @classmethod
    def of_module(cls, file: str) -> Scope:
        return cls(file=file, lines=executable_lines(file))


@dataclass(frozen=True)
class Coverage:
    """Covered lines and the lines they were measured against, keyed by file.

    ``lines`` is kept rather than its count, so what was covered and what was
    not are two views of the same fact and can never disagree.
    """

    covered: Mapping[str, frozenset[int]]
    lines: Mapping[str, frozenset[int]]

    @classmethod
    def of(cls, scope: Scope, raw_lines: frozenset[int]) -> Coverage:
        return cls(covered={scope.file: raw_lines & scope.lines}, lines={scope.file: scope.lines})

    @property
    def total(self) -> Mapping[str, int]:
        """How many lines each file has to cover."""
        return {file: len(lines) for file, lines in self.lines.items()}

    @property
    def uncovered(self) -> Mapping[str, frozenset[int]]:
        """The lines not covered, keyed like ``total``. A fully covered file keeps an empty set."""
        return {
            file: lines - self.covered.get(file, frozenset()) for file, lines in self.lines.items()
        }


@dataclass(frozen=True)
class Reach:
    """What one input reached in the target's file beyond its lines.

    ``function_lines`` is every line of the functions the input entered,
    whether or not the input ran it, and ``branches`` maps each branch line
    of them to the lines its ways lead to
    (``execution.branch_ways``). ``went`` holds each way the input went, as
    its branch line and the line it led to.
    """

    function_lines: frozenset[int] = frozenset()
    branches: Mapping[int, frozenset[int]] = field(default_factory=dict)
    went: frozenset[tuple[int, int]] = frozenset()


class Progress:
    """The lines each input covered, in run order, and what the inputs reached, for the stops.

    ``covered`` is one set per input that ran, within the scope, as
    ``no_gain`` reads it. ``full`` reads the rest.
    """

    def __init__(self, scope: Scope, imported: frozenset[int]) -> None:
        self.scope = scope
        self.covered: list[frozenset[int]] = []
        self._imported = imported
        self._lines: set[int] = set()
        self._entered: set[int] = set()
        self._branches: dict[int, set[int]] = {}
        self._went: dict[int, set[int]] = {}

    def add(self, lines: frozenset[int], reach: Reach) -> frozenset[int]:
        """Add the next input: the lines it covered and what it reached. The lines it covered
        that no earlier input and not the import did come back."""
        scoped = lines & self.scope.lines
        first = scoped - self._lines - self._imported
        self.covered.append(scoped)
        self._lines |= scoped
        self._entered |= reach.function_lines & self.scope.lines
        for line, ways in reach.branches.items():
            self._branches.setdefault(line, set()).update(ways)
        for line, way in reach.went:
            self._went.setdefault(line, set()).add(way)
        return first

    def full(self) -> bool:
        """Whether every line and branch is covered: every line of the functions the inputs
        entered is covered, the lines the import ran included, and every branch of them an
        input reached went each of its ways. False while no input entered a function."""
        if not self._entered or not self._entered <= self._lines | self._imported:
            return False
        return all(
            ways <= self._went.get(line, set())
            for line, ways in self._branches.items()
            if line in self._lines
        )
