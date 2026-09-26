"""Where each input of a run runs: in a child process of its own, or in pyct's process.

By default each input runs in a child process forked from pyct's process
after the target's import. The child starts from the target's module as the
import left it, because pyct's process never calls the target, and whatever
the input changes goes with the child. A fork per input costs about 1.6 ms
end to end on the machine this was measured on, closures work because
nothing is looked up by name, and nothing is pickled on the way in: the
child already holds the callable, the arguments and the deadline. The
child freezes garbage collection first thing, so a collection there skips
pyct's objects instead of copying every page they sit on (1.15 ms against
8.9 ms with a 190 MB heap). pyct's own process never freezes or unfreezes,
so a freeze a ``run()`` caller made stays the caller's.

The child writes each fact of its call into a journal in shared memory (see
``journal``), and pyct's process reads it once the child has ended, however
it ended (see ``process``).

A copy of a process can hang on a lock another thread held at the copy.
When the target's import left threads running (see ``Target.threads``),
each input runs in a fresh interpreter instead (see ``fresh``). Threads
that ran before the import, such as a test runner's watchdog, do not count.
The fresh interpreter imports the target by name, so a target no module
attribute names, such as a closure made from the imported module, runs in
pyct's process instead. Either way pyct says so once.

``--in-process`` runs every input in pyct's own process instead, exactly as
before isolation: state carries over, the target writes to pyct's stdout,
and a crash ends pyct.
"""

from __future__ import annotations

import contextlib
import functools
import logging
import mmap
import os
import sys
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass

from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure
from pyct.run.child import Served, flush_streams, serve
from pyct.run.fresh import fresh_for, in_a_fresh_interpreter
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import InputStartError, ending, watched
from pyct.run.target import Target

logger = logging.getLogger(__name__)

# one input in, what it did out: the arguments and the monotonic instant it must end by
type Call = Callable[[Mapping[str, object], float | None], ExecutionResult]


@dataclass(frozen=True)
class Isolation:
    """How a run calls its target for each input, and whether each input gets its own process."""

    call: Call
    isolated: bool


def isolation(target: Target, isolated: bool) -> Isolation:
    """Choose once, for the whole run, where its inputs run."""
    if not isolated:
        return _in_process(target)
    if target.threads == 0:
        alone = ExecutionContext(fn=target.fn, file=target.file, alone=True)
        return Isolation(call=functools.partial(in_a_child, alone), isolated=True)
    if not _named(target):
        logger.warning(
            "each input runs in pyct's process, because the target's import left threads"
            " running and no module attribute names the target for a fresh interpreter to import"
        )
        return _in_process(target)
    logger.warning(
        "each input runs in a fresh interpreter, because the target's import left threads running"
    )
    fresh = functools.partial(in_a_fresh_interpreter, fresh_for(target.spec, target.file))
    return Isolation(call=fresh, isolated=True)


def _in_process(target: Target) -> Isolation:
    ctx = ExecutionContext(fn=target.fn, file=target.file)
    return Isolation(call=functools.partial(execute, ctx), isolated=False)


def _named(target: Target) -> bool:
    """Whether a fresh interpreter importing the target's module by name finds this callable."""
    module_name, _, name = target.spec.partition("::")
    module = sys.modules.get(module_name)
    return module is not None and getattr(module, name, None) is target.fn


def in_a_child(
    ctx: ExecutionContext, args: Mapping[str, object], until: float | None
) -> ExecutionResult:
    """Run one input in a child process forked from this one, and read what it did."""

    def call(watch: JournalWriter) -> Failure | None:
        return execute(ctx, args, until, watch=watch).failure

    with _journal() as buffer:
        waited = watched(functools.partial(_forked, buffer, call), until)
        return ending(read(buffer), waited)


@contextlib.contextmanager
def _journal() -> Generator[mmap.mmap]:
    """An anonymous shared mapping the child inherits, freed once it is read."""
    try:
        buffer = mmap.mmap(-1, CAPACITY)
    except OSError as error:
        raise InputStartError(f"could not map the input's journal: {error}") from error
    try:
        yield buffer
    finally:
        buffer.close()


def _forked(buffer: mmap.mmap, call: Served) -> int:
    """Fork the input's process and return its pid. The child serves the call and exits.

    Only the child writes the journal, so only the child holds a view of it,
    and this process can unmap it once it is read.

    The four standard streams are flushed first, so the child cannot write
    this process's buffered text a second time.
    """
    flush_streams()
    try:
        pid = os.fork()
    except OSError as error:
        raise InputStartError(f"could not start a child process: {error}") from error
    if pid == 0:
        # coverage.py cannot see this line: it runs in the child, in a frame begun before the fork
        serve(JournalWriter(buffer), call)  # pragma: no cover
    return pid
