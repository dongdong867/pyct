"""Ask cvc5 whether a path can be taken, and for an input that takes it."""

import logging
import math
import subprocess
import time
from collections.abc import Mapping

from pyct.binding.shapes import ListShape
from pyct.core.branch import Branch
from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat, model_from
from pyct.solver.declared import Program
from pyct.solver.list_reader import RenderTimeError, RenderTooLargeError
from pyct.solver.lists import Origin, UnencodedError
from pyct.solver.locate import locate
from pyct.solver.render import program

logger = logging.getLogger(__name__)

# read one SMT-LIB program from stdin, print a model with the answer, say nothing else
ARGUMENTS = ("--produce-models", "--lang", "smt", "--quiet")

# asked after the program's last command, so the last line cvc5 prints is why it answered
# unknown, or an error after any other answer
WHY = "(get-info :reason-unknown)\n"

# cvc5's reply to WHY when its time limit ended the check
OUT_OF_TIME = "(:reason-unknown timeout)"

# how cvc5's reply to WHY starts after an answer other than unknown, which has no reason
NO_REASON = "(error "

# cvc5 answers unknown at --tlimit-per; pyct stops it this much later when it does not
GRACE_SECONDS = 1.0

# the longest wait Python's poll takes, 2**31 - 1 milliseconds, in whole seconds
LONGEST_WAIT_SECONDS = 2_147_483.0


def solve(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    timeout: float,
    lists: Mapping[str, ListShape] | None = None,
    values: Mapping[str, object] | None = None,
) -> Answer:
    """The input that takes ``prefix``, if there is one. ``timeout`` is the seconds the solve
    gets, writing the program included.

    ``leaves``, ``lists`` and ``values`` are what the input whose path it extends holds: each
    int and str the solver may change, each tracked list with its shape, and each leaf's value.

    The formula goes in on stdin rather than a file, so a run leaves nothing
    behind on disk.

    ``timeout`` is finite and above zero. The program is written first, and cvc5 is told what
    is left of it as its limit, so one solve ends near its limit however long the writing
    took. At the limit cvc5 answers ``unknown`` and, asked why, says ``timeout``: that
    is a ``Timeout()``, and an ``unknown`` for any other reason stays an
    ``Unknown()``. A cvc5 still running ``GRACE_SECONDS`` past the limit is
    stopped by pyct, and that is a ``Timeout()`` as well. A limit longer than Python can wait,
    about 24 days, is cut to what it can. An unsat answer to a program that holds the answer
    to more than the path (``Program.narrowed``) says only that no answer was found: it is an
    ``Unknown()``.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. The one exception is
    a ``sat`` whose model has a value line pyct cannot read: that is
    ``SolverAnswerError``, because a half-read model would quietly hand the
    seed's values back as the solver's.
    """
    until = time.monotonic() + timeout
    path = (prefix, leaves, lists)
    written = _written(path, until, Origin(values or {}))
    if not isinstance(written, Program):
        return written
    answer = _in_time(written, until)
    if isinstance(answer, Unsat) and (written.narrowed or written.held):
        return _unheld(written, path, until, values or {})
    return answer


def _in_time(written: Program, until: float) -> Answer:
    """What cvc5 answers in what is left of the solve's limit once the program is written."""
    left = until - time.monotonic()
    return Timeout() if left <= 0 else _asked(written, left)


# the path a solve asks about: its forks, and the leaves and lists of the input it extends
type _Path = tuple[tuple[Branch, ...], Mapping[str, type], Mapping[str, ListShape] | None]


def _unheld(written: Program, path: _Path, until: float, values: Mapping[str, object]) -> Answer:
    """An unsat answer to a program that holds the answer to more than the path.

    Clamps settled as the input had them leave it unknown. A repeated list's hold is let go and
    the path asked again: unsat still is unsat, and any other answer, one that would make the
    target build a list past the hold, is an unknown miss.
    """
    if written.narrowed:
        logger.debug("cvc5 found no answer with the clamps settled as the input had them")
        return Unknown()
    free = _written(path, until, Origin(values, hold=False))
    again = _in_time(free, until) if isinstance(free, Program) else free
    return again if isinstance(again, Unsat) else Unknown()


def _asked(written: Program, timeout: float) -> Answer:
    """What cvc5 answers the program within ``timeout`` seconds."""
    text = written.text + WHY
    timeout = min(timeout, LONGEST_WAIT_SECONDS - GRACE_SECONDS)
    argv = _argv(timeout)
    logger.debug("asking cvc5 %s about:\n%s", argv, text)
    try:
        finished = subprocess.run(
            argv,
            input=text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout + GRACE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("pyct stopped cvc5, which ran past its time limit")
        return Timeout()
    answer = _answer(finished.stdout, finished.stderr)
    if isinstance(answer, Sat):
        # cvc5 answered by the constants the program declared; the run reads leaves by name
        answer = Sat(written.read(answer.model))
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer


def _written(path: _Path, until: float, origin: Origin) -> Program | Timeout | Unknown:
    """The program for the path, written by ``until``.

    A read that runs long goes through a list cut again and again at clamps the path does not
    settle: it is written again with each clamp settled as the input had it (``Origin``). A
    program that outlives the solve's limit is a ``Timeout()``, as a solve that does is, and a
    path with a read nothing on it types is an ``Unknown()``, a miss rather than a crash.
    """
    prefix, leaves, lists = path
    try:
        try:
            return program(prefix, leaves, lists, until, origin)
        except RenderTooLargeError:
            logger.debug("writing the path again with its clamps settled as the input had them")
            settled = Origin(origin.values, settle=True, hold=origin.hold)
            return program(prefix, leaves, lists, until, settled)
    except RenderTimeError:
        logger.warning("writing the program for cvc5 ran past the time limit")
        return Timeout()
    except UnencodedError as error:
        logger.warning("pyct cannot write the path for cvc5: %s", error)
        return Unknown()


def _argv(timeout: float) -> list[str]:
    """The command. cvc5 counts its limit in milliseconds, and rounds up is the honest way.

    The limit is on the check, ``--tlimit-per``, where cvc5 answers
    ``unknown`` and exits. ``--tlimit`` would end the whole process with
    ``abort()``, which the system records as a crash. Rounding up also keeps
    any limit above zero at 1 or more, since cvc5 reads ``--tlimit-per=0``
    as no limit.
    """
    return [str(locate()), *ARGUMENTS, f"--tlimit-per={math.ceil(timeout * 1000)}"]


def _answer(stdout: str, stderr: str) -> Answer:
    """What cvc5 said. The first word decides; anything unrecognized is kept whole.

    The last line is cvc5's reply to ``WHY``, so a model is the lines between
    the answer and that reply. A ``sat`` whose last line is not that reply is
    an ``Error``: the line dropped as the reply might have been a value.
    """
    lines = stdout.strip().splitlines()
    head = lines[0] if lines else ""
    if head == "sat" and lines[-1].startswith(NO_REASON):
        return Sat(model_from(lines[1:-1]))
    if head == "unsat":
        return Unsat()
    if head == "unknown":
        return Timeout() if lines[-1] == OUT_OF_TIME else Unknown()
    return Error(f"{stdout}\n{stderr}".strip())
