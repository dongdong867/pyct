"""Whose raise was it, the target's or pyct's."""

from __future__ import annotations

import traceback
import types
from collections.abc import Callable, Iterator

from pyct.core.branch import PYCT_DIR
from pyct.core.values import is_downgrade_frame
from pyct.results.failure import Failure, FailureKind


def blame(fn: Callable[..., object], error: Exception) -> Failure:
    """Say whose the raise was.

    An exception raised while the target runs is a **pyct bug** when any frame
    below the target's code object in the traceback lives under pyct's package
    directory; otherwise it is **target raised**. Below means deeper in the
    traceback than the target's own frame, so it covers the calls the target
    made and not the ones that led to it. A downgrade frame is exempt: it runs
    only int's own operation, so a raise inside it is the target's. A pyct bug
    keeps the whole traceback, because the frames are what a person needs to
    fix pyct.
    """
    if any(_is_pyct_frame(tb.tb_frame.f_code) for tb in _below_target(fn, error)):
        return Failure(
            kind=FailureKind.PYCT_BUG,
            detail=one_line(error),
            traceback="".join(traceback.format_exception(error)),
        )
    return Failure(kind=FailureKind.TARGET_RAISED, detail=one_line(error))


def _is_pyct_frame(code: types.CodeType) -> bool:
    """A frame of pyct's own: under pyct's directory, and not a downgrade."""
    return code.co_filename.startswith(PYCT_DIR) and not is_downgrade_frame(code)


def _below_target(fn: Callable[..., object], error: Exception) -> tuple[types.TracebackType, ...]:
    """The traceback entries deeper than the target's own frame.

    A target with a code object that no frame ran never got its turn, so
    every entry is below it: the raise came from pyct's own setup.
    """
    entries = tuple(_entries(error.__traceback__))
    code = getattr(fn, "__code__", None)
    for index, entry in enumerate(entries):
        if _is_target_frame(entry, code):
            return entries[index + 1 :]
    return entries if code is not None else ()


def _is_target_frame(entry: types.TracebackType, code: types.CodeType | None) -> bool:
    """The target's own frame runs its code object.

    A callable without one, a ``functools.partial`` say, never gets a frame,
    so the first frame outside pyct stands in for it.
    """
    if code is not None:
        return entry.tb_frame.f_code is code
    return not entry.tb_frame.f_code.co_filename.startswith(PYCT_DIR)


def _entries(tb: types.TracebackType | None) -> Iterator[types.TracebackType]:
    """The traceback as a sequence, outermost frame first."""
    while tb is not None:
        yield tb
        tb = tb.tb_next


def one_line(error: BaseException) -> str:
    """The exception as a person reads it at the end of a traceback, on one line."""
    # a message with newlines comes back inside one entry, so split each entry too
    parts = (
        part.strip()
        for entry in traceback.format_exception_only(error)
        for part in entry.splitlines()
    )
    return " ".join(part for part in parts if part)
