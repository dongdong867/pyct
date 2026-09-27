"""The page on which the command's process names the module it is importing.

The process the shell started reads it once the command's process has
ended, to tell an ending during the import from any other (see ``launch``).
"""

from __future__ import annotations

import contextlib
import mmap
import struct
from collections.abc import Generator, Sequence

# the page starts with the length of the module name it holds, zero when it names none
_LENGTH = struct.Struct("<I")


class ImportWatch:
    """The page on which the command's process names the module it is importing."""

    def __init__(self, argv: Sequence[str]) -> None:
        """A page every process forked from this one shares, with room for the whole ``argv``.

        A module name is part of one argument, so any name the command line
        gives fits.
        """
        room = len("".join(argv).encode("utf-8", "surrogateescape"))
        self._page = mmap.mmap(-1, _LENGTH.size + room)

    @contextlib.contextmanager
    def importing(self, module_name: str) -> Generator[None]:
        """Name ``module_name`` on the page until the block ends, however it ends."""
        self._write(module_name.encode())
        try:
            yield
        finally:
            self._write(b"")

    def module(self) -> str | None:
        """The module the page names, or None."""
        (length,) = _LENGTH.unpack_from(self._page)
        if length == 0:
            return None
        return self._page[_LENGTH.size : _LENGTH.size + length].decode()

    def _write(self, name: bytes) -> None:
        self._page[_LENGTH.size : _LENGTH.size + len(name)] = name
        _LENGTH.pack_into(self._page, 0, len(name))
