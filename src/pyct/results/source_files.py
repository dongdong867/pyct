"""The source files a run reads code from, each read and parsed once per run, by its path."""

from __future__ import annotations

import ast

# a file's source and its tree
type Read = tuple[str, ast.Module]


class SourceFiles:
    """Each file's source and tree, read and parsed the first time it is asked for and kept by its
    path for the run; None for one that does not read or parse."""

    def __init__(self) -> None:
        self._read: dict[str, Read | None] = {}

    def read(self, file: str) -> Read | None:
        """The file's source and tree, or None when it does not read or parse."""
        if file not in self._read:
            self._read[file] = read_source(file)
        return self._read[file]


def read_source(file: str) -> Read | None:
    """The file's source and its tree, read now, or None when it does not read or parse."""
    try:
        with open(file, encoding="utf-8") as opened:
            source = opened.read()
        return source, ast.parse(source, filename=file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None
