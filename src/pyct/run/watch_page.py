"""The page the command's process shares with the process the shell started and its guard.

The command's process names on it the module it is importing, and the
input's process it runs. The process the shell started reads the module
once the command's process has ended, to tell an ending during the import
from any other (see ``launch``). The guard reads the input's process when
it kills the command's process, and kills that process too (see ``guard``).
"""

from __future__ import annotations

import contextlib
import mmap
import os
import struct
import tempfile
from collections.abc import Generator, Sequence

# the page starts with the pid of the input's process it names, zero when it names none, as a
# 32-bit signed integer, little-endian, the way the guard reads it
_INPUT = struct.Struct("<i")
# then the length of the module name it holds, zero when it names none, then the name
_LENGTH = struct.Struct("<I")
_NAME_AT = _INPUT.size + _LENGTH.size


class WatchPage:
    """The page on which the command's process names its import and its input's process."""

    def __init__(self, fd: int) -> None:
        """The page in the file ``fd`` opens, shared by every process that maps that file."""
        self.fd = fd
        self._page = mmap.mmap(fd, os.fstat(fd).st_size)

    @classmethod
    def for_command_line(cls, argv: Sequence[str]) -> WatchPage:
        """A new page, in an unlinked file, with room for the whole ``argv``.

        A module name is part of one argument, so any name the command line
        gives fits. A file rather than anonymous memory, so a command's
        process started as a fresh interpreter can map it too, and the guard
        can read it.
        """
        room = len("".join(argv).encode("utf-8", "surrogateescape"))
        fd, path = tempfile.mkstemp(prefix="pyct-watch-")
        os.unlink(path)
        os.ftruncate(fd, _NAME_AT + room)
        return cls(fd)

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
        (length,) = _LENGTH.unpack_from(self._page, _INPUT.size)
        if length == 0:
            return None
        return self._page[_NAME_AT : _NAME_AT + length].decode()

    def name_input(self, pid: int) -> None:
        """Name the input's process ``pid`` on the page; zero names none."""
        _INPUT.pack_into(self._page, 0, pid)

    def input(self) -> int | None:
        """The pid of the input's process the page names, or None."""
        (pid,) = _INPUT.unpack_from(self._page)
        return pid or None

    def _write(self, name: bytes) -> None:
        self._page[_NAME_AT : _NAME_AT + len(name)] = name
        _LENGTH.pack_into(self._page, _INPUT.size, len(name))
