"""Substituted code kept between runs, in pyct's own cache folder.

Parsing and substituting a large package costs far more than importing it
from Python's own bytecode, so each module's substituted code is kept and
used again while its source is the same. The folder is ``.pyct_cache`` in
the folder pyct runs from, as pytest keeps ``.pytest_cache``, or the one
``PYCT_CACHE_DIR`` names. Nothing is written inside the target's package
or its ``__pycache__``.

An entry is one file per module path, in a folder per version of the
transform, so a changed pyct never reads code an older one made. It holds
the digest of the source it was made from, the source file's stat when it
was read, then the code. The digest decides: a different one is a miss, so
an edit is substituted again whatever its size and time. An unchanged stat
stands in for reading the source only when it was recorded more than 2 s
after the file last changed, as git's index trusts a file's stat: on a file
clock no coarser than that, an edit made later changes the file's change
time, so it never goes unseen. A folder or file that cannot be read or
written is only a miss: the module is substituted again, and nothing is
kept, which pyct says once as a warning.

An entry is code that runs, so only this user's own entries are read, in a
folder that is this user's alone: made with mode 0700, and never one that
another user owns or may write to.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import importlib.util
import logging
import marshal
import os
import struct
import sys
import tempfile
import time
import types
from collections.abc import Callable
from pathlib import Path

from pyct.intercept import calls, compiled, constants, operators, positions, substitute

logger = logging.getLogger(__name__)

# the variable that names the cache folder, and the folder's name when it names none
CACHE_VARIABLE = "PYCT_CACHE_DIR"
_DEFAULT = ".pyct_cache"

# what `pyct run --help` says of the folder
CACHE_HELP = (
    "pyct keeps the target's substituted code in .pyct_cache/ in the folder it runs from, "
    "or in the folder PYCT_CACHE_DIR names. Deleting it is always safe."
)

# what the folder holds for git: it ignores everything in it, itself included
_IGNORE = "# made by pyct, which keeps its cache here\n*\n"

# an entry's head: the source's digest, its stat as five ints, and whether that stat is trusted
_HEAD = struct.Struct("<32s5q?")

# how long after a file's last change its stat is trusted: FAT's two seconds, the coarsest clock
_SETTLED_NS = 2_000_000_000

# a file's stat as an entry records it: when its content and its inode last changed, its size,
# and which file it is
type Stat = tuple[int, int, int, int, int]


def cache_folder() -> Path:
    """The folder pyct keeps its cache in: the one the variable names, or ``.pyct_cache`` here."""
    return Path(os.environ.get(CACHE_VARIABLE) or _DEFAULT).absolute()


def cached(
    root: Path,
    path: str,
    read: Callable[[], bytes],
    build: Callable[[bytes], types.CodeType],
) -> types.CodeType:
    """The substituted code for the module's source as it is now: kept under ``root``, or built.

    ``read`` gives the source and ``build`` substitutes it; each raises what
    it raises, and nothing is kept then. What ``build`` makes is kept for the
    next run. The stat is taken before the read, so an edit between the two
    leaves a stat the next run does not match.
    """
    if not _usable(root):
        return build(read())
    entry = os.path.join(root, "substituted", _version(), _name(path))
    held = _held(entry)
    stat = _stat(path)
    if held is not None and stat is not None and _settled(held, stat):
        code = _code(held)
        if code is not None:
            return code
    source = read()
    digest = hashlib.sha256(source).digest()
    kept = _code(held) if held is not None and held.startswith(digest) else None
    code = build(source) if kept is None else kept
    _write(root, entry, _head(digest, stat) + marshal.dumps(code))
    return code


@functools.cache
def _version() -> str:
    """A digest of the code that decides what an entry holds: the transform, its compile, and this
    module's format."""
    digest = hashlib.sha256()
    rules = (substitute.__file__, operators.__file__, calls.__file__, constants.__file__)
    rules += (positions.__file__,)
    for file in (*rules, compiled.__file__, __file__):
        digest.update(Path(str(file)).read_bytes())
    return digest.hexdigest()[:16]


def _name(path: str) -> str:
    """The entry's file name: the module's path, the Python that compiles it, its optimize level."""
    key = b"\0".join(
        (os.fsencode(path), importlib.util.MAGIC_NUMBER, str(sys.flags.optimize).encode())
    )
    return hashlib.sha256(key).hexdigest()[:32]


@functools.cache
def _usable(root: Path) -> bool:
    """Whether the folder is there or can be made, and is this user's alone."""
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        found = root.stat()
    except OSError as error:
        _cannot_keep(root, str(error))
        return False
    if not _own(found):
        _cannot_keep(root, "another user owns it or may write to it")
        return False
    return True


def _own(found: os.stat_result) -> bool:
    """Whether this user owns the file, and no one else may write to it."""
    return found.st_uid == os.getuid() and not found.st_mode & 0o022


# the cache folders pyct has already said it cannot keep code in, in this process
_WARNED: set[Path] = set()


def _cannot_keep(root: Path, why: str) -> None:
    """Say once per folder that code cannot be kept there, with the first reason met."""
    if root in _WARNED:
        return
    _WARNED.add(root)
    logger.warning(
        "pyct cannot keep substituted code in %s (%s), so every run substitutes the target's "
        "package again; %s names another folder",
        root,
        why,
        CACHE_VARIABLE,
    )


def _held(entry: str) -> bytes | None:
    """What the entry holds, or None when there is none, or it is not this user's alone."""
    try:
        with open(entry, "rb", buffering=0) as handle:
            return handle.readall() if _own(os.fstat(handle.fileno())) else None
    except OSError:
        return None


def _stat(path: str) -> Stat | None:
    """The source file's stat, or None when it cannot be read; the read then says why."""
    try:
        found = os.stat(path)
    except OSError:
        return None
    return (found.st_mtime_ns, found.st_ctime_ns, found.st_size, found.st_ino, found.st_dev)


def _settled(held: bytes, stat: Stat) -> bool:
    """Whether the entry recorded this very stat, long enough after the file's last change."""
    if len(held) < _HEAD.size:
        return False
    _, *recorded, trusted = _HEAD.unpack_from(held)
    return trusted and tuple(recorded) == stat


def _code(held: bytes) -> types.CodeType | None:
    """The code the entry holds after its head, or None when it holds none."""
    try:
        code = marshal.loads(held[_HEAD.size :])
    except (EOFError, ValueError, TypeError):
        return None
    return code if isinstance(code, types.CodeType) else None


def _head(digest: bytes, stat: Stat | None) -> bytes:
    """An entry's head: the source's digest, and its stat, trusted once the file has settled."""
    recorded = stat or (0, 0, 0, 0, 0)
    trusted = stat is not None and time.time_ns() - stat[1] > _SETTLED_NS
    return _HEAD.pack(digest, *recorded, trusted)


def _write(root: Path, entry: str, data: bytes) -> None:
    """Keep the entry whole: written to a file beside it, then put in its place at once.

    Two processes writing one entry, forked inputs or sweep's entries,
    leave one whole entry behind.
    """
    folder = os.path.dirname(entry)
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        ignore = root / ".gitignore"
        if not ignore.exists():
            ignore.write_text(_IGNORE)
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".", delete=False) as handle:
            handle.write(data)
        try:
            os.replace(handle.name, entry)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(handle.name)
            raise
    except OSError as error:
        _cannot_keep(root, str(error))
