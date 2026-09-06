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
    """Covered lines and the line count, keyed by file."""

    covered: Mapping[str, frozenset[int]]
    total: Mapping[str, int]

    @classmethod
    def of(cls, scope: Scope, raw_lines: frozenset[int]) -> Coverage:
        return cls(
            covered={scope.file: raw_lines & scope.lines}, total={scope.file: len(scope.lines)}
        )
