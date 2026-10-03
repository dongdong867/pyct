"""Ask cvc5 whether a path can be taken, and for an input that takes it."""

import logging
import math
import subprocess
from collections.abc import Mapping
from dataclasses import replace
from time import monotonic

from pyct.binding.shapes import DictShape, ListShape
from pyct.core.branch import Branch, Expression, Fact
from pyct.solver.answer import (
    Answer,
    Error,
    Sat,
    SolverAnswerError,
    Timeout,
    Unknown,
    Unsat,
    model_from,
)
from pyct.solver.answer_size import MOST_ITEMS
from pyct.solver.dict_keys import LookupsTooManyError
from pyct.solver.floats import FINITE
from pyct.solver.list_reader import ProgramTooLargeError, RenderTimeError, RenderTooLargeError
from pyct.solver.lists import READ_STEPS, Origin, UnencodedError
from pyct.solver.locate import locate
from pyct.solver.render import Program, float_leaves, program

logger = logging.getLogger(__name__)

# read one SMT-LIB program from stdin, print a model with the answer, say nothing else, and
# write each string in the model in full, up to the longest an answer holds
ARGUMENTS = (
    "--produce-models",
    "--lang",
    "smt",
    "--quiet",
    f"--strings-model-max-len={MOST_ITEMS}",
)

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

# the steps a read may take per second of the solve's limit before its program is written
# again with clamps settled; never fewer than READ_STEPS
STEPS_PER_SECOND = 100

# the steps a path's tracked-key lookups into its dicts may take together, per second of the
# solve's limit. cvc5 writes each call out over every key it may equal, and a key looked up and
# then read makes four calls, the lookup's and the read's own lookup, whether the value is of
# the kind read, and the value: into 3,000 keys, 3,001 steps each, 12,004 a key. cvc5 works
# through about 44,000 steps a second: 10 keys, 120,040 steps, solve in about 2.7 s, 20 keys in
# about 5.5 s, and 300 keys grow past 3.8 GB. So at the 10 s default 350,000 steps are asked,
# 29 keys looked up and read in 3,000 keys, and more are given up at once
LOOKUP_STEPS_PER_SECOND = 35_000

# the steps all reads of the unsettled program asked after a settled unsat may take together, per
# second of the solve's limit, so a path's outcome never turns on how long the first ask took.
# Each cut of a list at open clamps doubles them: ten cuts take about 10,000 and eleven about
# 20,500, so at the 10 s default ten are asked and eleven given up at once
UNSETTLED_STEPS_PER_SECOND = 2_000

# how often a read that runs long settles the clamps it went through before every clamp settles
SETTLE_ROUNDS = 4

# the path a solve asks about: its forks, and the leaves of the input it extends
type _Path = tuple[tuple[Branch, ...], Mapping[str, type]]


def solve(
    prefix: tuple[Branch | Fact, ...],
    leaves: Mapping[str, type],
    timeout: float,
    shapes: Mapping[str, ListShape | DictShape] | None = None,
    values: Mapping[str, object] | None = None,
) -> Answer:
    """The input that takes ``prefix``, if there is one. ``timeout`` is the seconds the solve
    gets, writing the program included.

    ``prefix`` is the path's forks with the facts it keeps beside them, in the order the path
    recorded them (see ``Plan.asked``). Each fork and each decided check a fact holds is
    asserted as it was recorded, and a fact is never negated; each place a fact keeps holds a
    key a walk read where it read it (see ``dicts``).

    ``leaves``, ``shapes`` and ``values`` are what the input whose path it extends holds: each
    leaf the solver may change, each tracked list and dict with its shape, and each leaf's
    value.

    The formula goes in on stdin rather than a file, so a run leaves nothing
    behind on disk.

    ``timeout`` is finite and above zero. The program is written first, and cvc5 is told what
    is left of it as its limit, so one solve ends near its limit however long the writing
    took. At the limit cvc5 answers ``unknown`` and, asked why, says ``timeout``: that
    is a ``Timeout()``, and an ``unknown`` for any other reason stays an
    ``Unknown()``. A cvc5 still running ``GRACE_SECONDS`` past the limit is
    stopped by pyct, and that is a ``Timeout()`` as well. A limit longer than Python can wait,
    about 24 days, is cut to what it can. Each ask after the first gets what the ones before
    left of ``timeout``, so all stay inside the one limit, and one with nothing left is a
    ``Timeout()`` without starting cvc5.

    A read through a list cut again and again at clamps the path leaves open doubles with each
    cut. One that runs past its steps, more the longer the limit, is written again with the
    clamps it went through settled as the input had them (see ``_written``). An unsat answer
    to that settled program asks the unsettled one in what is left of the limit, and only an
    unsat to that is an ``Unsat()``; an unsettled program whose reads together run past
    ``UNSETTLED_STEPS_PER_SECOND`` for each second of ``timeout`` is given up as an
    ``Unknown()``.

    A program that holds a repeated list's length, or a bound some form is exact inside, as a
    float floor division's, answers the target's own inputs when it is sat. An unsat to it asks
    once more with neither held (see ``_loosened``); decision
    float-floor-division-a-real-floor-inside-a-bound.

    A program that keeps each dict's keys no fork names and makes none up answers with the
    input's keys where the path does not ask for others. An unsat to it asks once more with
    them free. A program that keeps a key a walk read at its place answers an input that walks
    as the path did; an unsat to it runs every ask once more without the places, where only an
    unsat is the path's, and a model is an ``Unknown()``, since pyct cannot tell whether the
    answer it would write walks the dict as the path did (see ``_asked`` and ``dicts``).

    A prefix that names a float leaf is asked first with each such leaf held
    finite; decision float-finite-first-frees-the-unsat-core. See ``_finite_first``.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. A ``sat`` whose model
    has a value line pyct cannot read, or names a constant the program did
    not declare, is an ``Unknown()``, warned about with the reason: a
    half-read model would quietly hand the seed's values back as the
    solver's, and the fork is a miss rather than the run's end.
    """
    timeout = min(timeout, LONGEST_WAIT_SECONDS - GRACE_SECONDS)
    conditions, places = held(prefix)
    origin = replace(_origin(shapes or {}, values or {}, timeout), places=places)
    path = (conditions, leaves)
    answer, placed = _asked(path, origin, timeout)
    if isinstance(answer, Unsat) and placed:
        logger.debug("unsat with the keys a walk read kept in place: asking without")
        answer, _ = _asked(path, replace(origin, keep=False, pinned=False), timeout)
        return Unknown() if isinstance(answer, Sat) else answer
    return answer


def held(
    prefix: tuple[Branch | Fact, ...],
) -> tuple[tuple[Branch, ...], tuple[Expression, ...]]:
    """What a path holds: each fork, and each decided check a fact holds in its recorded sense,
    in order, and each place a fact keeps."""
    conditions = tuple(
        step
        if isinstance(step, Branch)
        else Branch(step.expression, step.taken, step.site, step.raising)
        for step in prefix
        if isinstance(step, Branch) or step.decided
    )
    places = tuple(
        step.place for step in prefix if isinstance(step, Fact) and step.place is not None
    )
    return conditions, places


def _asked(path: _Path, origin: Origin, timeout: float) -> tuple[Answer, bool]:
    """What the path is answered from ``origin``, every ask a program that held more than the
    path needs and was unsat taken in turn, and whether any program kept a key a walk read in
    its place.

    The places are what makes a model walk the dict as the path did; without them, a model may
    walk another order, and pyct cannot tell whether an answer it writes takes the path, so a
    model to the asks without places is an ``Unknown()`` (see ``solve``).
    """
    answer, written = _solved(path, origin)
    placed = written is not None and written.placed
    if isinstance(answer, Unsat) and written is not None and written.kept:
        logger.debug("unsat with each dict's other keys kept: asking with them free")
        origin = replace(origin, keep=False)
        answer, written = _solved(path, origin)
        placed = placed or (written is not None and written.placed)
    if isinstance(answer, Unsat) and written is not None and written.narrowed:
        logger.debug("unsat with clamps settled as the input had them: asking unsettled")
        origin = replace(origin, steps=None, most=int(timeout * UNSETTLED_STEPS_PER_SECOND))
        answer, written = _solved(path, origin)
    if isinstance(answer, Unsat) and written is not None and (written.held or written.bounded):
        return _loosened(path, origin), placed
    return answer, placed


def _origin(
    shapes: Mapping[str, ListShape | DictShape], values: Mapping[str, object], timeout: float
) -> Origin:
    """The input a solve extends, its lists apart from its dicts, and the solve's limits."""
    lists = {name: shape for name, shape in shapes.items() if isinstance(shape, ListShape)}
    dicts = {name: shape for name, shape in shapes.items() if isinstance(shape, DictShape)}
    steps = max(READ_STEPS, int(timeout * STEPS_PER_SECOND))
    until = monotonic() + timeout
    lookups = int(timeout * LOOKUP_STEPS_PER_SECOND)
    return Origin(lists, dicts, values, steps=steps, until=until, lookups=lookups)


def _loosened(path: _Path, origin: Origin) -> Answer:
    """An unsat answer to a program that holds a repeated list's length or a form's bound.

    The path is asked once more with neither held and every double allowed, where each form
    past its bound can be whatever Python gives there: an unsat to that unsettled program is
    the path's, whatever core cvc5 picked. A model is an ``Unknown()``, since past a hold the
    target would build a list too long, and past a bound it may not be Python's; so is a
    program that settled its clamps. A timeout or a failure is what it is on any other ask.
    """
    written, _ = _written(path, replace(origin, hold=False, bounded=False), frozenset())
    if not isinstance(written, Program):
        return written
    if written.narrowed:
        return Unknown()
    answer, _ = _ask_by(written, origin.until)
    return answer if isinstance(answer, Unsat | Timeout | Error) else Unknown()


def _solved(path: _Path, origin: Origin) -> tuple[Answer, Program | None]:
    """What cvc5 answers the path written from ``origin``, and the program it answered, None
    when none was written."""
    finite = float_leaves(*path, origin)
    written, origin = _written(path, origin, finite)
    if not isinstance(written, Program):
        return written, None
    return _finite_first(path, origin, written, finite), written


def _written(
    path: _Path, origin: Origin, finite: frozenset[str]
) -> tuple[Program | Timeout | Unknown, Origin]:
    """The program for the path, and the origin it was written from.

    A read that runs past ``origin.steps`` goes through a list cut again and again at clamps the
    path does not settle: it is written again with the clamps of each list part it went through
    settled as the input had them, round after round, and at the last every clamp settles and
    the read runs as long as it takes.
    """
    for _ in range(SETTLE_ROUNDS):
        try:
            return _write(path, origin, finite), origin
        except RenderTooLargeError as error:
            if error.passed <= origin.settle:
                break
            logger.debug("writing the path again with %d list parts settled", len(error.passed))
            origin = replace(origin, settle=origin.settle | error.passed)
    origin = replace(origin, everywhere=True, steps=None)
    return _write(path, origin, finite), origin


def _write(
    path: _Path, origin: Origin, finite: frozenset[str], *, cores: bool = False
) -> Program | Timeout | Unknown:
    """The program for the path, written by the origin's instant.

    A program that outlives the solve's limit is a ``Timeout()``, as a solve that does is. A
    path with a read nothing on it types, or one whose reads run past the steps the origin
    gives them all, is an ``Unknown()``, a miss rather than a crash.
    """
    try:
        return program(*path, origin, finite=finite, cores=cores)
    except RenderTimeError:
        logger.warning("writing the program for cvc5 ran past the time limit")
        return Timeout()
    except LookupsTooManyError as error:
        logger.debug("giving up the program's tracked-key lookups: %s", error)
        return Unknown()
    except ProgramTooLargeError as error:
        logger.debug("giving up the unsettled program: %s", error)
        return Unknown()
    except UnencodedError as error:
        logger.warning("pyct cannot write the path for cvc5: %s", error)
        return Unknown()


def _finite_first(path: _Path, origin: Origin, written: Program, finite: frozenset[str]) -> Answer:
    """What cvc5 answers the program, each float leaf in ``finite`` held finite at first.

    Only an ``Unsat`` asks again: once with the same leaves held and cvc5 asked for its unsat
    core, which says which of them the unsat rests on, and then with those leaves free and the
    rest still held. That repeats until an ask answers otherwise or the core names no held
    leaf. So a leaf may be NaN or an infinity only once an unsat that held it finite names it
    in its core. One core may name several leaves where freeing any one of them would do, and
    each is freed. The core costs its ask time only after an unsat, since asking for it slows
    some sat answers.
    """
    answer, _ = _ask_by(written, origin.until)
    while finite and isinstance(answer, Unsat):
        cored = _write(path, origin, finite, cores=True)
        if not isinstance(cored, Program):
            return cored
        answer, core = _ask_by(cored, origin.until)
        freed = finite & core
        if not isinstance(answer, Unsat) or not freed:
            return answer
        finite -= freed
        freer = _write(path, origin, finite)
        if not isinstance(freer, Program):
            return freer
        answer, _ = _ask_by(freer, origin.until)
    return answer


def _ask_by(written: Program, until: float | None) -> tuple[Answer, frozenset[str]]:
    """One ask with what is left before ``until``, a ``Timeout()`` with nothing left."""
    assert until is not None
    left = until - monotonic()
    if left <= 0:
        logger.debug("no time left to ask cvc5")
        return Timeout(), frozenset()
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
    answer = _read(finished.stdout, finished.stderr, written)
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer, _core(finished.stdout, written) if isinstance(answer, Unsat) else frozenset()


def _read(stdout: str, stderr: str, written: Program) -> Answer:
    """What cvc5 said, a sat model named by the leaves.

    A sat model with a value line pyct cannot read, or a name the program
    did not declare, is an ``Unknown()``; any other reply is what
    ``_answer`` makes of it.
    """
    try:
        answer = _answer(stdout, stderr)
        # cvc5 answered by the constants the program declared; the run reads leaves by name
        return Sat(written.read(answer.model)) if isinstance(answer, Sat) else answer
    except SolverAnswerError as error:
        logger.warning("%s", error)
        return Unknown()


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
