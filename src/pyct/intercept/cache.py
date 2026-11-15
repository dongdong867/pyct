"""Substituted code kept between runs, in pyct's own cache folder.

Parsing and substituting a large package costs far more than importing it
from Python's own bytecode, so each module's substituted code is kept and
used again while its source is the same. The folder is ``.pyct_cache`` in
the folder pyct runs from, as pytest keeps ``.pytest_cache``, or the one
``PYCT_CACHE_DIR`` names. Nothing is written inside the target's package
or its ``__pycache__``.

An entry is one file per module path, and per variant of the transform
such as pyct's loop hooks, in a folder per version of the transform, so a
changed pyct never reads code an older one made. It holds
the digest of the source it was made from, the source file's stat when it
was read, then the code. The digest decides: a different one is a miss, so
an edit is substituted again whatever its size and time. An unchanged stat
stands in for reading the source only when it was recorded more than 2 s
after the file last changed, as git's index trusts a file's stat: on a file
clock no coarser than that, an edit made later changes the file's change
time, so it never goes unseen. A folder or file that cannot be read or
written is only a miss: the module is substituted again, and nothing is
kept, which pyct says once as a warning.

The version is a digest of pyct's own files that decide what an entry
holds. Reading them costs more than a warm import of a small package, so
the folder keeps the version beside those files' paths and stats, in a
record of its own for each set of paths, under the same rule: it is used
while every stat is the one recorded, and kept only when every file had
settled. Any other version is digested again. A record that cannot be
written costs only that digest, so pyct logs it at DEBUG alone.

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

from pyct.core.entry import bound, hashed, math_calls, type_calls
from pyct.intercept import (
    bool_returns,
    calls,
    compiled,
    constants,
    loops,
    operators,
    percents,
    positions,
    substitute,
    unpacks,
    watch,
)
from pyct.results import pieces, sources

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

# a record under the cache folder that keeps the transform's version, one per set of files it is
# made from, so checkouts sharing the folder keep one each: a digest of the files' paths and
# stats, then the version, 16 hex digits
_VERSION = struct.Struct("<32s16s")
_HEX = frozenset(b"0123456789abcdef")

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
    variant: str = "",
) -> types.CodeType:
    """The substituted code for the module's source as it is now: kept under ``root``, or built.

    ``read`` gives the source and ``build`` substitutes it; each raises what
    it raises, and nothing is kept then. What ``build`` makes is kept for the
    next run. The stat is taken before the read, so an edit between the two
    leaves a stat the next run does not match. ``variant`` names code
    ``build`` makes another way, such as with pyct's loop hooks, which is kept
    in an entry of its own; the empty one is the entry plain substitution
    has always had.
    """
    folder = _entries(root)
    if folder is None:
        return build(read())
    entry = os.path.join(folder, _name(path, variant))
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
def _entries(root: Path) -> str | None:
    """The folder of this transform's entries under ``root``, or None when ``root`` keeps none."""
    return os.path.join(root, "substituted", _version(root)) if _usable(root) else None


def _version(root: Path) -> str:
    """The transform's version: the digest of `_version_files`, as kept under ``root`` in the
    record for those paths.

    The kept one is used while every file has the stat it had when the
    version was kept; any other is a digest made again, kept when every
    file has settled.
    """
    files = _version_files()
    stats = [_stat(file) for file in files]
    key = hashlib.sha256(repr((files, stats)).encode()).digest()
    named = hashlib.sha256(repr(files).encode()).hexdigest()[:16]
    record = os.path.join(root, "substituted", f"version-{named}")
    held = _held(record)
    if held is not None and len(held) == _VERSION.size:
        recorded, version = _VERSION.unpack(held)
        if recorded == key and set(version) <= _HEX:
            return version.decode()
    made = _digest(files)
    if all(_trusted_now(stat) for stat in stats):
        try:
            _put(root, record, _VERSION.pack(key, made.encode()))
        except OSError as error:
            # only a digest saved: the entries are still read and written as before
            logger.debug("pyct cannot keep the transform's version in %s (%s)", root, error)
    return made


def _trusted_now(stat: Stat | None) -> bool:
    """Whether a file was last changed more than 2 s ago, so its stat is trusted."""
    return stat is not None and time.time_ns() - stat[1] > _SETTLED_NS


def _version_files() -> tuple[str, ...]:
    """The files of the code that decides what an entry holds, in the order they are digested:
    the transform and each of its rules, the `math`, `builtins` and `operator` names and the range
    and view method names it takes, each other module of pyct's a rule takes a name, a size, a
    text or a piece from, its compile, and this module's format."""
    rules = (substitute.__file__, operators.__file__, calls.__file__, constants.__file__)
    rules += (positions.__file__, bound.__file__, math_calls.__file__, type_calls.__file__)
    rules += (unpacks.__file__, percents.__file__, bool_returns.__file__, watch.__file__)
    rules += (loops.__file__,)
    # what the rules take from outside the transform: a size, the callee's text, and a piece
    rules += (hashed.__file__, sources.__file__, pieces.__file__)
    return tuple(str(file) for file in (*rules, compiled.__file__, __file__))


def _digest(files: tuple[str, ...]) -> str:
    """The version the files make: the first 16 hex digits of the SHA-256 of their contents, read
    in order."""
    digest = hashlib.sha256()
    for file in files:
        digest.update(_whole(file))
    return digest.hexdigest()[:16]


def _whole(file: str) -> bytes:
    """A file's contents, read with the operating system's calls alone."""
    handle = os.open(file, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        while chunk := os.read(handle, 1 << 20):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(handle)


def _name(path: str, variant: str) -> str:
    """The entry's file name: the module's path, the Python that compiles it, its optimize level,
    and the variant when there is one."""
    parts = [os.fsencode(path), importlib.util.MAGIC_NUMBER, str(sys.flags.optimize).encode()]
    key = b"\0".join([*parts, variant.encode()] if variant else parts)
    return hashlib.sha256(key).hexdigest()[:32]


def _usable(root: Path) -> bool:
    """Whether the folder is there or can be made, and is this user's alone."""
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        found = root.stat()
    except OSError as error:
        _cannot_keep(root, str(error))
        return False
    if not owned_alone(found):
        _cannot_keep(root, "another user owns it or may write to it")
        return False
    return True


def owned_alone(found: os.stat_result) -> bool:
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
        handle = os.open(entry, os.O_RDONLY)
    except OSError:
        return None
    try:
        found = os.fstat(handle)
        return os.read(handle, found.st_size) if owned_alone(found) else None
    except OSError:
        return None
    finally:
        os.close(handle)


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
        code = marshal.loads(memoryview(held)[_HEAD.size :])
    except (EOFError, ValueError, TypeError):
        return None
    return code if isinstance(code, types.CodeType) else None


def _head(digest: bytes, stat: Stat | None) -> bytes:
    """An entry's head: the source's digest, and its stat, trusted once the file has settled."""
    recorded = stat or (0, 0, 0, 0, 0)
    return _HEAD.pack(digest, *recorded, _trusted_now(stat))


def _write(root: Path, entry: str, data: bytes) -> None:
    """Keep the entry whole: written to a file beside it, then put in its place at once.

    Two processes writing one entry, forked inputs or sweep's entries,
    leave one whole entry behind.
    """
    try:
        _put(root, entry, data)
    except OSError as error:
        _cannot_keep(root, str(error))


def _put(root: Path, path: str, data: bytes) -> None:
    """Write a file under ``root`` whole, beside it first and then in its place, or raise the
    `OSError` that stopped it, leaving no file of its own behind."""
    folder = os.path.dirname(path)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    ignore = root / ".gitignore"
    if not ignore.exists():
        ignore.write_text(_IGNORE)
    with tempfile.NamedTemporaryFile(dir=folder, prefix=".", delete=False) as handle:
        handle.write(data)
    try:
        os.replace(handle.name, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(handle.name)
        raise
