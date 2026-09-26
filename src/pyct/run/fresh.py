"""One input in a fresh interpreter, for a run whose target's import left threads running.

A copy of a process that runs threads can hang on a lock one of them held
at the copy, so such a run copies nothing: each input starts a new Python,
which imports the target by name and runs the one call. It costs about
11 ms before the target's own import, which takes seconds for a large
library, so it is the way only when forking is unsafe.

Only the input crosses on the way in: pyct's import path, the target's name
and file, the arguments and the deadline, pickled into a file the new
interpreter reads. The facts come back through the same journal a forked
child writes, backed by a file both processes map. The new interpreter's
stdin is empty and its stdout is stderr from its first instruction.
"""

from __future__ import annotations

import contextlib
import functools
import mmap
import os
import pickle
import signal
import sys
import tempfile
from collections.abc import Generator, Mapping
from pathlib import Path
from typing import NoReturn

from pyct.core.branch import PYCT_DIR
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure
from pyct.run.child import serve
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import InputStartError, ending, watched
from pyct.run.target import load_target

# what the new interpreter runs: the pyct this process runs, then main on the two files
_BOOT = (
    "import sys; sys.path.insert(0, sys.argv[1]); from pyct.run.fresh import main; "
    "main(int(sys.argv[2]), int(sys.argv[3]))"
)
_PYCT_ROOT = str(Path(PYCT_DIR).parent)


def in_a_fresh_interpreter(
    spec: str, file: str, args: Mapping[str, object], until: float | None
) -> ExecutionResult:
    """Run one input of the target ``spec`` names in a new interpreter, and read what it did."""
    with _journal() as (journal, buffer), _request(spec, file, args, until) as request:
        waited = watched(functools.partial(_spawned, request, journal), until)
        return ending(read(buffer), waited)


def main(request: int, journal: int) -> NoReturn:
    """The new interpreter's side: read the input, import the target by name, run it once."""
    writer = JournalWriter(mmap.mmap(journal, CAPACITY))
    serve(writer, functools.partial(_requested, request))


def _requested(request: int, watch: JournalWriter) -> Failure | None:
    """The one call the request asks for, told to the journal as it happens."""
    with os.fdopen(request, "rb") as handed:
        sys.path[:] = pickle.load(handed)
        spec, file, args, until = pickle.load(handed)
    ctx = ExecutionContext(fn=load_target(spec).fn, file=file, alone=True)
    return execute(ctx, args, until, watch=watch).failure


@contextlib.contextmanager
def _journal() -> Generator[tuple[int, mmap.mmap]]:
    """A journal in an unlinked file, mapped here, whose descriptor the new interpreter maps."""
    with contextlib.ExitStack() as stack:
        try:
            backing = stack.enter_context(tempfile.TemporaryFile())
            os.ftruncate(backing.fileno(), CAPACITY)
            buffer = stack.enter_context(mmap.mmap(backing.fileno(), CAPACITY))
        except OSError as error:
            raise InputStartError(f"could not map the input's journal: {error}") from error
        yield backing.fileno(), buffer


@contextlib.contextmanager
def _request(
    spec: str, file: str, args: Mapping[str, object], until: float | None
) -> Generator[int]:
    """The input, pickled into an unlinked file: the import path first, then the call.

    The path comes first, so the arguments unpickle where their own modules import.
    """
    with contextlib.ExitStack() as stack:
        try:
            handed = stack.enter_context(tempfile.TemporaryFile())
            pickle.dump(list(sys.path), handed)
            pickle.dump((spec, file, dict(args), until), handed)
            handed.flush()
        except (OSError, pickle.PicklingError, TypeError, AttributeError) as error:
            raise InputStartError(
                f"could not hand the input to a fresh interpreter: {error}"
            ) from error
        handed.seek(0)
        yield handed.fileno()


def _spawned(request: int, journal: int) -> int:
    """Start the new interpreter and return its pid.

    Ctrl-C has its default action from the start, and stdin and stdout are
    set before any Python runs there.
    """
    for handed in (request, journal):
        os.set_inheritable(handed, True)
    try:
        return os.posix_spawn(
            sys.executable,
            [sys.executable, "-c", _BOOT, _PYCT_ROOT, str(request), str(journal)],
            os.environ,
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_DUP2, 2, 1),
            ],
            setsigdef=(signal.SIGINT,),
            setsigmask=(),
        )
    except OSError as error:
        raise InputStartError(f"could not start a fresh interpreter: {error}") from error
