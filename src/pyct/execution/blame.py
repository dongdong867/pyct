"""Whose raise was it, the target's or pyct's."""

from __future__ import annotations

import traceback
import types
from collections.abc import Callable, Iterator

from pyct.core.branch import PYCT_DIR
from pyct.core.values import raised_by_target
from pyct.results.failure import Failure, FailureKind


def blame(fn: Callable[..., object], error: BaseException, *, called: bool) -> Failure:
    """Say whose the raise was.

    An exception raised while the target runs is a **pyct bug** when any frame
    below the target's code object in the traceback lives under pyct's package
    directory; otherwise it is **target raised**. Below means deeper in the
    traceback than the target's own frame, so it covers the calls the target
    made and not the ones that led to it. A raise the base type's own operation
    made carries a mark saying so, and that mark wins: pyct ran the operation
    but did not fail. A raise before the target was ``called`` is pyct's own
    setup. A pyct bug keeps the whole traceback, because the frames are what a
    person needs to fix pyct.
    """
    if not raised_by_target(error) and any(
        _is_pyct_frame(tb.tb_frame.f_code) for tb in _below_target(fn, error, called)
    ):
        return Failure(
            kind=FailureKind.PYCT_BUG,
            detail=one_line(error),
            traceback="".join(traceback.format_exception(error)),
        )
    return Failure(kind=FailureKind.TARGET_RAISED, detail=one_line(error))


def _is_pyct_frame(code: types.CodeType) -> bool:
    """A frame of pyct's own: one whose code lives under pyct's directory."""
    return code.co_filename.startswith(PYCT_DIR)


def _below_target(
    fn: Callable[..., object], error: BaseException, called: bool
) -> tuple[types.TracebackType, ...]:
    """The traceback entries deeper than the target's own frame.

    A target that was never called got no turn, so every entry is below it.
    The first entry is otherwise the frame that called the target.
    """
    entries = tuple(_entries(error.__traceback__))
    if not called:
        return entries
    code = getattr(fn, "__code__", None)
    if code is None:
        return _below_codeless_target(entries)
    for index, entry in enumerate(entries):
        if entry.tb_frame.f_code is code:
            return entries[index + 1 :]
    return entries[1:]


def _below_codeless_target(
    entries: tuple[types.TracebackType, ...],
) -> tuple[types.TracebackType, ...]:
    """Below a callable without a code object, a ``functools.partial`` say.

    One that wraps Python runs the frame right under the caller's, so that
    frame stands in for it. One that wraps C runs no frame at all, so every
    entry under the caller's ran under it.
    """
    if len(entries) > 1 and not entries[1].tb_frame.f_code.co_filename.startswith(PYCT_DIR):
        return entries[2:]
    return entries[1:]


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
