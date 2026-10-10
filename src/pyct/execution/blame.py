"""Whose raise was it, the target's or pyct's."""

from __future__ import annotations

import os
import sys
import traceback
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pyct.core.branch import PYCT_DIR
from pyct.core.substitutes import PASSING
from pyct.core.values import raised_by_target
from pyct.results.failure import Failure, FailureKind

# the most frames pyct's own code runs on top of the target's for one operation, a fork written to
# the journal at the deepest, about a dozen, with room to spare. A longer run of pyct's frames
# at the top of the stack is pyct recursing on its own
MOST_OWN_FRAMES = 40

# pyct's own top package, by which code with no file is told to be pyct's
_PYCT = __name__.partition(".")[0]

# where the standard library's and installed packages' code lives: a frame from there is no
# frame of the target's own, unless it lies in the target's own package. Read off `os`'s file
# and the path rather than `sysconfig`, which a target may ship a module of its own as
_OUTSIDE = tuple(
    os.path.join(path, "")
    for path in (
        os.path.dirname(os.__file__),
        *(
            entry
            for entry in sys.path
            if os.path.basename(entry) in ("site-packages", "dist-packages")
        ),
    )
)


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

    A RecursionError is about the whole stack, and a target's recursion hits
    the limit wherever its deepest frame happens to be, often in the few
    frames pyct runs for a fork on top of it. So it is pyct's only when the
    run of pyct's frames at the top of the stack, where it was raised, holds
    more than pyct's own code runs for one operation (``MOST_OWN_FRAMES``):
    pyct recursing on its own.
    """
    below = _below_target(fn, error, called)
    if not raised_by_target(error) and _raised_by_pyct(error, below, _home(fn)):
        return Failure(
            kind=FailureKind.PYCT_BUG,
            detail=one_line(error),
            traceback="".join(traceback.format_exception(error)),
        )
    return Failure(kind=FailureKind.TARGET_RAISED, detail=one_line(error))


def _raised_by_pyct(
    error: BaseException, below: tuple[types.TracebackType, ...], home: _Home
) -> bool:
    """Whether the frames ``below`` the target make the raise pyct's own."""
    if isinstance(error, RecursionError):
        return _top_run(below, home) > MOST_OWN_FRAMES
    return any(_is_pyct_frame(entry.tb_frame.f_code) for entry in below)


@dataclass(frozen=True)
class _Home:
    """Where the target's own code lives: its top package's folders, or its module's file, and
    the top package's name, which code Python generates for it carries."""

    paths: tuple[str, ...]
    package: str


def _top_run(below: tuple[types.TracebackType, ...], home: _Home) -> int:
    """How many of pyct's frames run at the top of the stack, where the raise happened.

    Counted from the deepest frame up, to the first frame that is neither
    pyct's nor passed over. Passed over: a file under the standard library's
    or the installed packages' folders (``_OUTSIDE``) that is not the
    target's own, such as `json`'s that pyct's journal calls or `copy`'s, and
    code with no file, its name in angle brackets, whose globals' ``__name__``
    is not in pyct's package or the target's. Code with no file whose globals
    name a module of pyct's counts as pyct's frame, and one of the target's
    package ends the run.
    """
    run = 0
    for entry in reversed(below):
        frame = entry.tb_frame
        if _is_pyct_frame(frame.f_code) or _fileless_in(frame, _PYCT):
            run += 1
        elif not _passed_over(frame, home):
            break
    return run


def _passed_over(frame: types.FrameType, home: _Home) -> bool:
    """Whether a frame that is not pyct's is passed over in the run: library code, as
    ``_top_run`` says, never the target's own."""
    file = frame.f_code.co_filename
    if file.startswith("<"):
        return not _fileless_in(frame, home.package)
    return not file.startswith(home.paths) and file.startswith(_OUTSIDE)


def _fileless_in(frame: types.FrameType, package: str) -> bool:
    """Whether the frame runs code with no file, its name in angle brackets, whose globals'
    ``__name__`` names a module of ``package``."""
    if not frame.f_code.co_filename.startswith("<"):
        return False
    name = frame.f_globals.get("__name__")
    return isinstance(name, str) and bool(package) and name.partition(".")[0] == package


def _home(fn: Callable[..., object]) -> _Home:
    """Where the target's own code lives, as far as its module says.

    A package's folders come from its ``__path__``, which a namespace
    package spreads over several; a module with no package is its own file.
    """
    name = getattr(fn, "__module__", None) or ""
    module = sys.modules.get(name)
    package = name.partition(".")[0]
    top = sys.modules.get(package, module)
    folders = getattr(top, "__path__", None)
    if folders is not None:
        return _Home(tuple(os.path.join(str(folder), "") for folder in folders), package)
    file = getattr(top, "__file__", None)
    return _Home((file,) if isinstance(file, str) else (), package)


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
