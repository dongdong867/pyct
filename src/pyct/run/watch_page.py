"""The page the command's process shares with the process the shell started and its guard.

The command's process names on it the module it is importing, the input's
process it runs, and the process group of a command it runs, as sweep runs
each entry's ``pyct run``. The process the shell started reads the module
once the command's process has ended, to tell an ending during the import
from any other (see ``launch``). The guard reads the input's process and
the group when it kills the command's process, and kills them too (see
``guard``).
"""

from __future__ import annotations

import contextlib
import mmap
import os
import struct
import tempfile
from collections.abc import Generator, Sequence

# the page starts with two C ints in the machine's byte order, the way the guard reads them: the
# pid of the input's process it names, at INPUT_AT, then the id of the process group it names, at
# GROUP_AT, each zero when it names none. The page's start is aligned, and each int sits at a
# multiple of its size, so each is written in one store, and a reader never sees half of one
_INT = struct.Struct("=i")
INPUT_AT = 0
GROUP_AT = INPUT_AT + _INT.size
# then the length of the module name it holds, zero when it names none, then the name
_LENGTH = struct.Struct("<I")
_LENGTH_AT = GROUP_AT + _INT.size
_NAME_AT = _LENGTH_AT + _LENGTH.size


class WatchPage:
    """The page on which the command's process names its import, its input's process and the
    group of a command it runs."""

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
        (length,) = _LENGTH.unpack_from(self._page, _LENGTH_AT)
        if length == 0:
            return None
        return self._page[_NAME_AT : _NAME_AT + length].decode()

    def name_input(self, pid: int) -> None:
        """Name the input's process ``pid`` on the page; zero names none."""
        self._store(INPUT_AT, pid)

    def input(self) -> int | None:
        """The pid of the input's process the page names, or None."""
        return self._load(INPUT_AT) or None

    def name_group(self, group: int) -> None:
        """Name the process group ``group`` on the page; zero names none."""
        self._store(GROUP_AT, group)

    def group(self) -> int | None:
        """The id of the process group the page names, or None."""
        return self._load(GROUP_AT) or None

    def close(self) -> None:
        """Unmap the page and close its file, in this process."""
        self._page.close()
        os.close(self.fd)

    def _store(self, at: int, value: int) -> None:
        with memoryview(self._page) as page, page[at : at + _INT.size].cast("i") as word:
            word[0] = value

    def _load(self, at: int) -> int:
        with memoryview(self._page) as page, page[at : at + _INT.size].cast("i") as word:
            return word[0]

    def _write(self, name: bytes) -> None:
        self._page[_NAME_AT : _NAME_AT + len(name)] = name
        _LENGTH.pack_into(self._page, _LENGTH_AT, len(name))
