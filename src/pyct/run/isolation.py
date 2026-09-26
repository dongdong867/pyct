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
So just before each input, pyct counts the threads its process runs, as
the system counts them, and forks only when the main thread is the only
one. Whose thread another one is, the target's import, an earlier import
of the same module, or the host program, pyct does not try to tell. From
the first input that finds another thread on, the run starts a fresh
interpreter per input instead (see ``fresh``). That interpreter imports
the target by name, so a target no module attribute names, such as a
closure, runs in pyct's process instead. Either way pyct says so once.

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
import random
import sys
from collections.abc import Callable, Generator, Mapping
from enum import StrEnum

from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.results.failure import Failure
from pyct.run.child import Served, flush_streams, serve
from pyct.run.fresh import fresh_for, in_a_fresh_interpreter
from pyct.run.journal import CAPACITY, JournalWriter, read
from pyct.run.process import InputStartError, ending, watched
from pyct.run.target import Target
from pyct.run.threads import running

logger = logging.getLogger(__name__)

# one input in, what it did out: the arguments and the monotonic instant it must end by
type Call = Callable[[Mapping[str, object], float | None], ExecutionResult]


class Isolation(StrEnum):
    """Where a run's inputs run.

    ``auto`` forks each input from pyct's process while that process runs no
    thread besides the main one, counted as the system counts them just
    before the input starts. Once another thread runs, that input and every
    later one start a fresh interpreter instead. ``fork``, ``fresh`` and
    ``in-process`` hold one way for every input; the command line offers
    auto and ``--in-process``.
    """

    AUTO = "auto"
    FORK = "fork"
    FRESH = "fresh"
    IN_PROCESS = "in-process"


class Inputs:
    """How one run calls its target for each input, and where each input ran.

    ``ran`` names, in order, where each input ran. In ``auto`` the switch to
    fresh interpreters is said once on stderr; so is the switch to pyct's
    own process, for a target no module attribute names, which a fresh
    interpreter could not import.
    """

    def __init__(self, target: Target, isolation: Isolation) -> None:
        if isolation is Isolation.FRESH and not _named(target):
            raise ValueError("a fresh interpreter imports the target by name, and none names it")
        self.isolation = isolation
        self.ran: list[Isolation] = []
        self._target = target
        self._switched: Isolation | None = None
        alone = ExecutionContext(fn=target.fn, file=target.file, alone=True)
        self._calls: dict[Isolation, Call] = {
            # random's state as the run finds it after the target's import, taken once
            Isolation.FORK: functools.partial(in_a_child, alone, random.getstate()),
            Isolation.FRESH: functools.partial(
                in_a_fresh_interpreter, fresh_for(target.spec, target.file)
            ),
            Isolation.IN_PROCESS: functools.partial(
                execute, ExecutionContext(fn=target.fn, file=target.file)
            ),
        }

    @property
    def isolated(self) -> bool:
        """Whether every input ran in a process of its own."""
        return self.isolation is not Isolation.IN_PROCESS and Isolation.IN_PROCESS not in self.ran

    def __call__(self, args: Mapping[str, object], until: float | None) -> ExecutionResult:
        where = self._where()
        self.ran.append(where)
        return self._calls[where](args, until)

    def _where(self) -> Isolation:
        """Where the next input runs."""
        if self.isolation is not Isolation.AUTO:
            return self.isolation
        if self._switched is None and running() > 1:
            self._switched = self._instead()
        return self._switched or Isolation.FORK

    def _instead(self) -> Isolation:
        """Where the rest of the run goes once pyct's process runs other threads, said once."""
        if _named(self._target):
            logger.warning(
                "each input runs in a fresh interpreter, because pyct's process runs other threads"
            )
            return Isolation.FRESH
        logger.warning(
            "each input runs in pyct's process, because pyct's process runs other threads and"
            " no module attribute names the target for a fresh interpreter to import"
        )
        return Isolation.IN_PROCESS


def _named(target: Target) -> bool:
    """Whether a fresh interpreter importing the target's module by name finds this callable."""
    module_name, _, name = target.spec.partition("::")
    module = sys.modules.get(module_name)
    return module is not None and getattr(module, name, None) is target.fn


def in_a_child(
    ctx: ExecutionContext,
    random_state: tuple[object, ...],
    args: Mapping[str, object],
    until: float | None,
) -> ExecutionResult:
    """Run one input in a child process forked from this one, and read what it did.

    ``random`` reseeds itself in every forked child, so the child puts back
    ``random_state``, the state the run took once after the target's import,
    before the call. Whatever pyct's process draws between inputs, each
    input starts from the state the import left, so a target that seeds
    ``random`` at import draws the same in every input.
    """

    def call(watch: JournalWriter) -> Failure | None:
        random.setstate(random_state)
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
