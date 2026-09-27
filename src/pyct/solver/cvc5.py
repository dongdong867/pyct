"""Ask cvc5 whether a path can be taken, and for an input that takes it."""

import logging
import math
import subprocess
from collections.abc import Mapping
from time import monotonic

from pyct.core.branch import Branch
from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat, model_from
from pyct.solver.locate import locate
from pyct.solver.render import FINITE, Program, float_leaves, program

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


def solve(prefix: tuple[Branch, ...], leaves: Mapping[str, type], timeout: float) -> Answer:
    """The input that takes ``prefix``, if there is one. ``timeout`` is the seconds cvc5 gets.

    The formula goes in on stdin rather than a file, so a run leaves nothing
    behind on disk.

    ``timeout`` is finite and above zero, and cvc5 is told it as its limit. At
    the limit cvc5 answers ``unknown`` and, asked why, says ``timeout``: that
    is a ``Timeout()``, and an ``unknown`` for any other reason stays an
    ``Unknown()``. A cvc5 still running ``GRACE_SECONDS`` past the limit is
    stopped by pyct, and that is a ``Timeout()`` as well, so every solve ends
    near its limit. A limit longer than Python can wait, about 24 days, is
    cut to what it can.

    A prefix that names a float leaf is asked first with each such leaf held
    finite; decision float-finite-first-frees-the-unsat-core. Only an
    ``Unsat`` asks again: once with the same leaves held and cvc5 asked for
    its unsat core, which says which of them the unsat rests on, and then
    with those leaves free and the rest still held. That repeats until an
    ask answers otherwise or the core names no held leaf. So a leaf may be
    NaN or an infinity only once an unsat that held it finite names it in
    its core. One core may name several leaves where freeing any one of them
    would do, and each is freed. The core costs its ask time only after an
    unsat, since asking for it slows some sat answers. Each ask after the
    first gets what the ones before left of ``timeout``, so all stay inside
    the one limit, and one with nothing left is a ``Timeout()`` without
    starting cvc5.

    A program that holds a bound some form is exact inside, as a float
    floor division's, answers Python's inputs when it is sat. When it ends
    unsat, the path is asked once more with the bounds left out and every
    double allowed, where each form past its bound can be whatever Python
    gives there: an unsat then is Python's, whatever core cvc5 picked, and
    any other answer is ``Unknown()``, since a model past a bound may not be
    Python's; decision float-floor-division-a-real-floor-inside-a-bound.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. The one exception is
    a ``sat`` whose model has a value line pyct cannot read: that is
    ``SolverAnswerError``, because a half-read model would quietly hand the
    seed's values back as the solver's.
    """
    timeout = min(timeout, LONGEST_WAIT_SECONDS - GRACE_SECONDS)
    deadline = monotonic() + timeout
    finite = float_leaves(prefix, leaves)
    first = program(prefix, leaves, finite=finite)
    answer, _ = _ask(first, timeout)
    while finite and isinstance(answer, Unsat):
        cored = _ask_by(program(prefix, leaves, finite=finite, cores=True), deadline)
        if cored is None:
            return Timeout()
        answer, core = cored
        freed = finite & core
        if not isinstance(answer, Unsat) or not freed:
            break
        finite -= freed
        freer = _ask_by(program(prefix, leaves, finite=finite), deadline)
        if freer is None:
            return Timeout()
        answer, _ = freer
    if first.bounded and isinstance(answer, Unsat):
        return _unbounded(prefix, leaves, deadline)
    return answer


def _unbounded(prefix: tuple[Branch, ...], leaves: Mapping[str, type], deadline: float) -> Answer:
    """The path with its bounds left out and every double allowed: ``Unsat()`` if even that is.

    A model is ``Unknown()``, since past a bound it may not be Python's; a
    timeout or a failure is what it is on any other ask.
    """
    asked = _ask_by(program(prefix, leaves, bounded=False), deadline)
    if asked is None:
        return Timeout()
    answer, _ = asked
    return answer if isinstance(answer, Unsat | Timeout | Error) else Unknown()


def _ask_by(written: Program, deadline: float) -> tuple[Answer, frozenset[str]] | None:
    """One ask with what is left before ``deadline``, or None with nothing left to ask with."""
    left = deadline - monotonic()
    if left <= 0:
        logger.debug("no time left to ask cvc5 again with more doubles")
        return None
    return _ask(written, left)


def _ask(written: Program, timeout: float) -> tuple[Answer, frozenset[str]]:
    """One ask of cvc5: the program, then why it answered, within ``timeout`` seconds.

    Also the leaves an unsat answer's core holds finite, when the program
    held any.
    """
    text = written.text + WHY
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
        return Timeout(), frozenset()
    answer = _answer(finished.stdout, finished.stderr)
    if isinstance(answer, Sat):
        # cvc5 answered by the constants the program declared; the run reads leaves by name
        answer = Sat(written.read(answer.model))
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer, _core(finished.stdout, written) if isinstance(answer, Unsat) else frozenset()


def _core(stdout: str, written: Program) -> frozenset[str]:
    """The leaves an unsat answer's dumped core holds finite, by their names.

    cvc5 prints the core right after the answer, its assertion names on one
    line or one per line; every other line after an unsat is a refusal that
    names no assertion. Each name is ``FINITE`` and the leaf's symbol.
    """
    words = stdout.replace("(", " ").replace(")", " ").split()
    symbols = [word.removeprefix(FINITE) for word in words if word.startswith(FINITE)]
    return frozenset(written.names_by_symbol[symbol] for symbol in symbols)


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
