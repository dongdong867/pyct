"""One call on model-written code, run in a child process forked from pyct's, with a time limit.

The LLM's code can loop, raise, crash or change state, so pyct's own
process only compiles it (`pyct.intercept.model_code`) and never runs it,
not even its ``def`` statements. Each call forks a child, as an input does
(`pyct.run.isolation`): the child runs the code's module in a namespace of
its own, with `len`, `ord` and `chr` bound as in a target's module, calls
the function on the arguments bound to leaves named by their keys, and
writes each fork, fact and downgrade to a journal as an input's process
does, then the answer as JSON to a second mapping. Whatever the call
changes in its own process goes with the child; what it does outside the
process, such as writing a file, only the asking tool's form check bounds.

A child forks only while pyct's process runs one thread, counted as
isolation counts them; otherwise the call does not run, and the tool that
asked decides what to do. Decision
llm-model-written-code-runs-only-in-a-forked-child-or-not-at-all.
"""

from __future__ import annotations

import contextlib
import functools
import json
import mmap
import struct
import types
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field

from pyct.core.entry.plain_json import plain_json
from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from pyct.intercept.wrap import bound_builtins
from pyct.results.failure import Failure
from pyct.run.isolation import forked, mapped_journal
from pyct.run.journal import JournalWriter
from pyct.run.journal_reader import JournalReader
from pyct.run.process import InputStartError, ending, refuse_after_a_stop, watched
from pyct.run.threads import running

# the most bytes of JSON one answer crosses back in
ANSWER_CAPACITY = 1024 * 1024

# why no call on model-written code runs beside a second thread of pyct's process, as each
# asking tool says it
CANNOT_FORK = "cannot fork"

# the answer's mapping: its state and its length, two native u64, then its bytes
_HEAD = struct.Struct("=QQ")
_NONE, _ANSWER, _UNENCODED = 0, 1, 2


@dataclass(frozen=True)
class ModelCall:
    """A call on model-written code: the module code, the function it defines, the arguments,
    bound to leaves named by their keys, and further names its module sees, such as ``math``."""

    code: types.CodeType
    function: str
    args: Mapping[str, object]
    names: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelRun:
    """How a call on model-written code went.

    ``answer`` is what the call returned, as JSON text, with each tracked
    value as its plain value, and a NaN or an infinity as Python's json
    writes it, which Python's json reads back; None when the call did not
    return, or when ``unencoded`` says why its value is not one JSON holds or
    does not fit.
    ``result`` holds the forks, facts and downgrades the child recorded,
    and in ``failure`` the raise that ended the call, or how the child
    ended: past its time limit, a crash, or an exit.
    """

    answer: str | None
    result: ExecutionResult
    unencoded: str | None = None


@dataclass(frozen=True)
class CannotFork:
    """pyct's process runs another thread, so no child forks and the call does not run."""


def run_model(call: ModelCall, until: float) -> ModelRun | CannotFork:
    """Run the call in a child process forked from this one, and read what it did.

    ``until`` is the monotonic instant the call must end by: the child's own
    alarm ends it there, and pyct kills it shortly after, as an input's
    process. Raises `InputStartError` when pyct cannot start the child, as
    an input's start does, and ``Stopped`` once pyct's process was told to stop.
    """
    refuse_after_a_stop()
    if not can_fork():
        return CannotFork()
    with mapped_journal() as buffer, _answer_mapping() as answers:
        reader = JournalReader(buffer)
        served = functools.partial(_serve, call, until, answers)
        waited = watched(functools.partial(forked, buffer, served), until, reader.look)
        result = ending(reader.finish(), waited)
        answer, unencoded = _read(answers)
    return ModelRun(answer, result, unencoded)


def can_fork() -> bool:
    """Whether a child may fork now: pyct's process runs one thread."""
    return running() <= 1


def _serve(
    call: ModelCall, until: float, answers: mmap.mmap, watch: JournalWriter
) -> Failure | None:
    """In the child: call the function under the time limit, then write its answer."""
    returned: list[object] = []
    context = ExecutionContext(fn=_calling(call, returned), file=call.code.co_filename, alone=True)
    failure = execute(context, call.args, until, watch=watch).failure
    if returned:
        _write(answers, returned[0])
    return failure


def _calling(call: ModelCall, returned: list[object]) -> Callable[..., None]:
    """The call as the child makes it: the code's module run in a namespace of its own, then
    its function called on the bound arguments, its answer kept in ``returned``."""

    def called(**bound: object) -> None:
        namespace: dict[str, object] = {"__builtins__": bound_builtins(), **call.names}
        exec(call.code, namespace)
        function = namespace[call.function]
        assert callable(function)
        returned.append(function(**bound))

    return called


@contextlib.contextmanager
def _answer_mapping() -> Generator[mmap.mmap]:
    """An anonymous shared mapping for the answer, which the child inherits."""
    try:
        answers = mmap.mmap(-1, _HEAD.size + ANSWER_CAPACITY)
    except OSError as error:
        raise InputStartError(f"could not map the answer: {error}") from error
    try:
        yield answers
    finally:
        answers.close()


def _write(answers: mmap.mmap, value: object) -> None:
    """Write the answer as JSON, or why it cannot be: its bytes first, then its head."""
    try:
        text = json.dumps(plain_json(value)).encode()
    except (TypeError, ValueError, RecursionError) as error:
        _written(answers, _UNENCODED, str(error).encode())
        return
    if len(text) > ANSWER_CAPACITY:
        note = f"the answer's {len(text)} bytes are over {ANSWER_CAPACITY}"
        _written(answers, _UNENCODED, note.encode())
        return
    _written(answers, _ANSWER, text)


def _written(answers: mmap.mmap, state: int, payload: bytes) -> None:
    answers[_HEAD.size : _HEAD.size + len(payload)] = payload
    _HEAD.pack_into(answers, 0, state, len(payload))


def _read(answers: mmap.mmap) -> tuple[str | None, str | None]:
    """The answer's JSON text and why it was not kept, as the child left them."""
    state, length = _HEAD.unpack_from(answers, 0)
    text = answers[_HEAD.size : _HEAD.size + length].decode("utf-8", "replace")
    if state == _ANSWER:
        return text, None
    return None, (text if state == _UNENCODED else None)
