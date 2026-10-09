"""Whose raise was it, the target's or pyct's."""

from __future__ import annotations

import traceback
import types
from collections.abc import Callable, Iterator

from pyct.core.branch import PYCT_DIR
from pyct.core.substitutes import PASSING
from pyct.core.values import raised_by_target
from pyct.results.failure import Failure, FailureKind


def blame(fn: Callable[..., object], error: BaseException, *, called: bool) -> Failure:
    """Say whose the raise was.

    An exception raised while the target runs is a **pyct bug** when any frame
    below the target's code object in the traceback lives under pyct's package
    directory; otherwise it is **target raised**. Below means deeper in the
    traceback than the target's own frame, so it covers the calls the target
    made and not the ones that led to it. A raise out of a call pyct made for
    the target, the base type's own operation or the compile of one of its
    modules, carries a mark saying so, and that mark wins: pyct ran the call
    but did not fail. The one frame a substituted `is` or `in` adds is read
    through, since the compare the target wrote had none. A raise before the
    target was ``called`` is pyct's own setup. A pyct bug keeps the whole
    traceback, because the frames are what a person needs to fix pyct.

    A RecursionError is about the whole stack, so it is pyct's only when
    pyct's own frames hold at least half of the frames below the target: a
    target's recursion hits the limit wherever the deepest frame happens to
    be, often in the few frames pyct runs for a fork on top of it.
    """
    below = _below_target(fn, error, called)
    if not raised_by_target(error) and _pyct_s(error, below):
        return Failure(
            kind=FailureKind.PYCT_BUG,
            detail=one_line(error),
            traceback="".join(traceback.format_exception(error)),
        )
    return Failure(kind=FailureKind.TARGET_RAISED, detail=one_line(error))


def _pyct_s(error: BaseException, below: tuple[types.TracebackType, ...]) -> bool:
    """Whether the frames ``below`` the target make the raise pyct's own."""
    pyct = sum(_is_pyct_frame(entry.tb_frame.f_code) for entry in below)
    if isinstance(error, RecursionError):
        return 2 * pyct >= len(below) > 0
    return pyct > 0


def _is_pyct_frame(code: types.CodeType) -> bool:
    """A frame of pyct's own: one whose code lives under pyct's directory.

    A function substituted code calls in place of `is` or `in` is not one.
    It runs no work of its own, only Python's operation or the target's own
    method, so a raise under it is the target's unless a frame of core's
    sits below. `own`'s mark would not do: it would mark a raise out of
    core's own code under it as the target's too.
    """
    return code.co_filename.startswith(PYCT_DIR) and code not in PASSING


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
    if len(entries) > 1 and not _is_pyct_frame(entries[1].tb_frame.f_code):
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
