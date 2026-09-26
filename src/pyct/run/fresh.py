"""One input in a fresh interpreter, for a run whose process runs other threads.

A copy of a process that runs threads can hang on a lock one of them held
at the copy, so from the first input that finds pyct's process running
another thread, the run forks no more: each input starts a new Python,
which imports the target by name and runs the one call. It costs about
11 ms before the target's own import, which takes seconds for a large
library, so it is the way only when forking is unsafe.

Only the input crosses on the way in: pyct's import path, the target's name
and file, the arguments and the deadline, pickled into a file the new
interpreter reads. Every fresh interpreter of one run gets the same hash
seed, so a target whose path follows the order of a set of strings takes
the same path for the same input in each of them. The facts
come back through the same journal a forked child writes, backed by a
file both processes map. The new interpreter's stdin is empty and its
stdout is stderr from its first instruction.
"""

from __future__ import annotations

import contextlib
import functools
import mmap
import os
import pickle
import signal
import subprocess
import sys
import tempfile
from collections.abc import Generator, Mapping
from dataclasses import dataclass
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


# the largest seed PYTHONHASHSEED takes
_MOST_SEED = 2**32 - 1


@dataclass(frozen=True)
class Fresh:
    """What every fresh interpreter of one run shares: the target's name and file, one hash seed."""

    spec: str
    file: str
    hash_seed: str


def fresh_for(spec: str, file: str) -> Fresh:
    """The run's fresh interpreters, hashing with the seed pyct was given, or one picked now."""
    # unset or empty, Python hashes at random
    given = os.environ.get("PYTHONHASHSEED") or "random"
    # from the system, never from random's own generator, which is the target's
    drawn = int.from_bytes(os.urandom(4), "little") % _MOST_SEED + 1
    seed = str(drawn) if given == "random" else given
    return Fresh(spec=spec, file=file, hash_seed=seed)


def in_a_fresh_interpreter(
    fresh: Fresh, args: Mapping[str, object], until: float | None
) -> ExecutionResult:
    """Run one input of the run's target in a new interpreter, and read what it did."""
    handed = _request(fresh.spec, fresh.file, args, until)
    with _journal() as (journal, buffer), handed as request:
        start = functools.partial(_spawned, request, journal, fresh.hash_seed)
        waited = watched(start, until)
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


def _command(request: int, journal: int) -> list[str]:
    """The new interpreter's command line: pyct's own interpreter flags, then the boot.

    ``-P`` keeps the working directory off the import path while pyct boots,
    so a module there named like one of the standard library's cannot stand
    in for it. The target's import still sees pyct's own path, which the
    request carries. pyct's own flags follow, as CPython's helper gives
    them: ``-O``, ``-B``, ``-S``, ``-s``, ``-v``, ``-b``, ``-q``, ``-d``, the
    ``-W`` options, and the ``-X`` options dev, faulthandler, tracemalloc,
    importtime, frozen_modules, showrefcount and utf8. Other ``-X`` options,
    such as int_max_str_digits, and ``-u`` do not follow. Left out are the
    flags that would make the new interpreter ignore the run's hash seed:
    ``-E``, and ``-I``, which stands in as ``-s``.
    """
    # CPython's own helper, the one multiprocessing starts its workers with; typeshed omits it
    given = subprocess._args_from_interpreter_flags()  # pyrefly: ignore[missing-attribute]
    flags = ["-s" if flag == "-I" else flag for flag in given if flag != "-E"]
    return [sys.executable, *flags, "-P", "-c", _BOOT, _PYCT_ROOT, str(request), str(journal)]


def _spawned(request: int, journal: int, hash_seed: str) -> int:
    """Start the new interpreter and return its pid.

    SIGINT is unblocked from its first instruction, and takes its default
    action once ``serve`` settles the process; Python's startup installs its
    own handler in between. Stdin and stdout are set before any Python runs.
    """
    for handed in (request, journal):
        os.set_inheritable(handed, True)
    try:
        return os.posix_spawn(
            sys.executable,
            _command(request, journal),
            {**os.environ, "PYTHONHASHSEED": hash_seed},
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_DUP2, 2, 1),
            ],
            setsigdef=(signal.SIGINT,),
            setsigmask=(),
        )
    except OSError as error:
        raise InputStartError(f"could not start a fresh interpreter: {error}") from error
