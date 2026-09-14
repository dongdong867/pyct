"""Which lines a module has, and which of them a run covered."""

from __future__ import annotations

import types
from collections.abc import Iterator, Mapping
from dataclasses import dataclass


def executable_lines(file: str) -> frozenset[int]:
    """Every line in the module that can fire a line event.

    Read from the compiled module's line tables, so ``def`` lines and
    module-level statements count too, though they run at import, not
    under a seed. Line 0 marks compiler-made instructions and is dropped.
    """
    with open(file, encoding="utf-8") as source:
        code = compile(source.read(), file, "exec")
    lines = {line for code_object in _walk(code) for _, _, line in code_object.co_lines() if line}
    return frozenset(lines)


def _walk(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _walk(constant)


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
        """The lines no input ran, keyed like ``total``. A fully covered file keeps an empty set."""
        return {
            file: lines - self.covered.get(file, frozenset()) for file, lines in self.lines.items()
        }
