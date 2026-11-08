"""Ask cvc5 whether a path can be taken, and for an input that takes it."""

import logging
import math
import subprocess
from collections.abc import Mapping
from dataclasses import replace
from time import monotonic, perf_counter

from pyct.binding.shapes import DictShape, ListShape
from pyct.core.foundation.branch import Branch, Expression, Fact
from pyct.solver import dict_orders
from pyct.solver.answer import (
    Answer,
    Error,
    Sat,
    SolverAnswerError,
    Timeout,
    Unknown,
    Unsat,
)
from pyct.solver.dict_keys import LookupsTooManyError
from pyct.solver.given import Given, answered, argv, options, took
from pyct.solver.held_items import float_leaves
from pyct.solver.list_reader import ProgramTooLargeError, RenderTimeError, RenderTooLargeError
from pyct.solver.lists import READ_STEPS, Origin
from pyct.solver.read_kinds import asked_of_each
from pyct.solver.render import Program, program
from pyct.solver.replies import answer_of, core_of
from pyct.solver.size_holds import grown_by
from pyct.solver.split_lists import UnknownCountError
from pyct.solver.unencoded import UnencodedError
from pyct.solver.walk_keys import UnwrittenError, Walks, missed

logger = logging.getLogger(__name__)

# asked after the program's last command, so the last line cvc5 prints is why it answered
# unknown, or an error after any other answer
WHY = "(get-info :reason-unknown)\n"

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

# the most seconds the ask with chosen walk keys takes, or the solve's limit when that is shorter:
# past it the ask is stopped, or given up at once where its lookup steps would run past it, and
# the solve goes on to the ask without places (let-the-solver-choose-a-small-dict-s-walk-key)
CHOSEN_SECONDS = 1.0

# the steps all reads of the unsettled program asked after a settled unsat may take together, per
# square root of a second of the solve's limit, so a path's outcome never turns on how long the
# first ask took. Each cut of a list at open clamps doubles the steps, and cvc5's time grows with
# their square, so the steps a limit allows grow with its square root. cvc5 1.4.2, three runs
# at a load of about 4:
#
#   cuts   steps  seconds
#      7   1,271  0.17-0.18
#      8   2,551  0.64-0.68
#      9   5,111  2.64-2.76
#     10  10,231  11.3-12.3
#
# 1 s allows 2,700 steps, 2 s 3,818, 5 s 6,037 and the 10 s default 8,538. So eight cuts are
# asked at 1 s and 2 s, and nine at 5 s and 10 s; ten are given up at once at 10 s. An asked
# program takes at most about three quarters of the limit
UNSETTLED_STEPS_PER_ROOT_SECOND = 2_700

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
    ``UNSETTLED_STEPS_PER_ROOT_SECOND`` times the square root of ``timeout`` is given up as
    an ``Unknown()``.

    A program that holds a repeated list's length, or a bound some form is exact inside, as a
    float floor division's, answers the target's own inputs when it is sat. An unsat to it asks
    once more with neither held (see ``_loosened``); decision
    float-floor-division-a-real-floor-inside-a-bound.

    A program that keeps each dict's keys no fork names and makes none up answers with the
    input's keys where the path does not ask for others, and one that holds a list of mixed
    kinds to the input's length keeps its items' kinds. An unsat to it asks once more with
    them free. A program that keeps a key a walk read at its place answers an input that walks
    as the path did; an unsat to it runs every ask once more without the places, where only an
    unsat is the path's, and a model is an ``Unknown()``, since pyct cannot tell whether the
    answer it would write walks the dict as the path did (see ``_asked`` and ``dicts``).

    A walk key, the key a dict's own walk reads at a pass, is the input's key there on the first
    ask; an unsat to it is asked with the keys the forks name chosen (``walk_keys``,
    ``_chosen``, ``_after_unsat``; let-the-solver-choose-a-small-dict-s-walk-key).

    A read that may land on another kind than Python read makes an unsat one more thing to
    check: each other kind is asked in turn (see ``read_kinds``).

    A prefix that names a float leaf or reads a float item is asked first with each such float
    held finite; decision float-finite-first-frees-the-core-s-leaves-and-lists. Each list length
    and dict size the solver chooses is asked first held small (``size_holds``); a string keeps
    only its cap. See ``_held_first``.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. A ``sat`` whose model
    has a value line pyct cannot read, or names a constant the program did
    not declare, is an ``Unknown()``, warned about with the reason: a
    half-read model would quietly hand the seed's values back as the
    solver's, and the fork is a miss rather than the run's end.
    """
    timeout = min(timeout, LONGEST_WAIT_SECONDS - GRACE_SECONDS)
    origin = _origin(shapes or {}, values or {}, timeout)
    try:
        walks = Walks(prefix, origin.dicts)
        fixed = walks.fixed(prefix)
    except UnwrittenError as error:
        logger.warning("pyct cannot write the path for cvc5: %s", error)
        return Unknown()
    if walks.settled(fixed) and not walks.choosing(prefix):
        return Unknown()
    conditions, places = held(fixed)
    origin = replace(origin, places=places)
    answer, placed, written = _asked((conditions, leaves), origin, timeout)
    if not isinstance(answer, Unsat):
        return answer
    answer = _after_unsat((prefix, leaves), walks, origin, placed, timeout)
    if not isinstance(answer, Unsat) or written is None:
        return answer

    def ask(kinds: Mapping[int, str]) -> Answer:
        return _asked((conditions, leaves), replace(origin, read_kinds=kinds), timeout)[0]

    return asked_of_each(written.other_kinds, written.untried, ask)


def _after_unsat(
    path: tuple[tuple[Branch | Fact, ...], Mapping[str, type]],
    walks: Walks,
    origin: Origin,
    placed: bool,
    timeout: float,
) -> Answer:
    """What a path the first ask found unsat is answered: asked with its walk keys chosen, then
    without places, and where a fork names a walk key or an escape keeps one, without every step
    that names one, an escape's fact among them; unless the flipped fork names one, which makes
    the unsat an ``Unknown()`` (see ``solve``)."""
    prefix, leaves = path
    if walks.choosing(prefix):
        chosen = _chosen(prefix, leaves, walks, origin)
        if isinstance(chosen, Sat):
            return chosen
        if not (isinstance(chosen, Unknown) and chosen.guarded):
            missed(prefix)
    answer: Answer = Unsat()
    if placed:
        logger.debug("unsat with the keys a walk read kept in place: asking without")
        unplaced = (held(walks.fixed(walks.unread(prefix)))[0], leaves)
        answer, *_ = _asked(unplaced, replace(origin, keep=False, pinned=False), timeout)
        if isinstance(answer, Sat):
            return Unknown()
    if isinstance(answer, Unsat) and walks.aimed:
        return Unknown()
    if isinstance(answer, Unsat) and (walks.forked or walks.pinned):
        logger.debug("unsat with each walk key at the input's key: asking without them")
        unnamed = (held(walks.unnamed(prefix))[0], leaves)
        answer, *_ = _asked(unnamed, replace(origin, keep=False, pinned=False), timeout)
        return answer if isinstance(answer, Unsat | Timeout | Error) else Unknown()
    return answer


def _chosen(
    prefix: tuple[Branch | Fact, ...], leaves: Mapping[str, type], walks: Walks, origin: Origin
) -> Answer:
    """The path asked with its chosen walk keys left to the solver (see ``walk_keys``), in at
    most ``CHOSEN_SECONDS`` or half of what is left of the solve's limit, so the ask without
    places keeps the other half, with the lookup steps that time allows. Only a sat answer is
    the solve's; any other goes on to the ask without places, as an unsat with the input's keys
    does."""
    assert origin.until is not None
    limit = min(CHOSEN_SECONDS, (origin.until - monotonic()) / 2)
    if limit <= 0:
        return Timeout()
    opened, walk_leaves, walk_values, orders = walks.opened(prefix)
    conditions, places = held(opened)
    ordered = [dict_orders.order(name, passes) for name, passes in orders.items()]
    chosen = replace(
        origin,
        places=(*places, *ordered),
        values={**origin.values, **walk_values},
        until=monotonic() + limit,
        lookups=int(limit * LOOKUP_STEPS_PER_SECOND),
    )
    answer, *_ = _asked((conditions, {**leaves, **walk_leaves}), chosen, limit)
    logger.debug("with the walk keys chosen: %s", type(answer).__name__)
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


def _asked(path: _Path, origin: Origin, timeout: float) -> tuple[Answer, bool, Program | None]:
    """What the path is answered from ``origin``, every ask a program that held more than the
    path needs and was unsat taken in turn, whether any program kept a key a walk read in its
    place, and the last program asked.

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
        most = int(UNSETTLED_STEPS_PER_ROOT_SECOND * math.sqrt(timeout))
        origin = replace(origin, steps=None, most=most)
        answer, written = _solved(path, origin)
    if isinstance(answer, Unsat | Unknown) and written is not None and written.fixed:
        logger.debug("a read from a split's end held to c* pieces: asking at the input's own")
        origin = replace(origin, fixed_reads=False)
        answer, written = _solved(path, origin)
    if isinstance(answer, Unsat) and written is not None and (written.held or written.bounded):
        return _loosened(path, origin), placed, written
    return answer, placed, written


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

    The path is asked once more with neither held, every double allowed and every length and
    size free to its cap, where each form past its bound can be whatever Python gives there: an
    unsat to that unsettled program is the path's, whatever core cvc5 picked. A model is an
    ``Unknown()``, since past a hold the target would build a list too long, and past a bound it
    may not be Python's; so is a program that settled its clamps. A timeout or a failure is what
    it is on any other ask.
    """
    loose = replace(origin, hold=False, bounded=False, small=False)
    written, _ = _written(path, loose, frozenset())
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
    return _held_first(path, origin, written, finite), written


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
    path with an operation no form writes on what it meets, or with reads past the steps the
    origin gives them all, is an ``Unknown()``, a miss rather than a crash.
    """
    try:
        return program(*path, origin, finite=finite, cores=cores)
    except RenderTimeError:
        logger.warning("writing the program for cvc5 ran past the time limit")
        return Timeout()
    except LookupsTooManyError as error:
        logger.debug("giving up the program's tracked-key lookups: %s", error)
        return Unknown(guarded=True)
    except ProgramTooLargeError as error:
        logger.debug("giving up the unsettled program: %s", error)
        return Unknown(guarded=True)
    except UnknownCountError as error:
        logger.debug("giving up a program that reads a count with no c*: %s", error)
        return Unknown()
    except UnencodedError as error:
        logger.warning("pyct cannot write the path for cvc5: %s", error)
        return Unknown()


def _held_first(path: _Path, origin: Origin, written: Program, finite: frozenset[str]) -> Answer:
    """What cvc5 answers the program, each float leaf in ``finite`` held finite at first, and
    each float a list or a dict in ``finite`` reads, and each list length and dict size the solver
    chooses held small (``size_holds``).

    Only an ``Unsat`` asks again: once with the same holds and cvc5 asked for its unsat core,
    which says which of them the unsat rests on, and then with those floats free, those sizes
    grown, and the rest as they were. That repeats until an ask answers otherwise or the core
    names no hold. So a leaf may be NaN or an infinity only once an unsat that held it finite
    names it in its core, and a list's or a dict's float once the core names any float it holds,
    which frees all of them; a size grows only once a core names its hold, and one core may free
    floats and grow sizes at once. One core may name several holds where loosening any one of
    them would do, and each is loosened. The core costs its ask time only after an unsat, since
    asking for it slows some sat answers, and a program that holds nothing asks no core.
    """
    answer, _ = _ask_by(written, origin.until)
    while (written.finite or written.sizes) and isinstance(answer, Unsat):
        cored = _write(path, origin, finite, cores=True)
        if not isinstance(cored, Program):
            return cored
        answer, core = _ask_by(cored, origin.until)
        freed, grown = finite & core, grown_by(cored.sizes, core)
        if not isinstance(answer, Unsat) or not (freed or grown):
            return answer
        finite -= freed
        origin = replace(origin, sizes={**origin.sizes, **grown})
        freer = _write(path, origin, finite)
        if not isinstance(freer, Program):
            return freer
        written = freer
        answer, _ = _ask_by(written, origin.until)
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

    Also what an unsat answer's core names, when the program held anything it may name
    (``replies.core_of``).
    """
    text = written.text + WHY
    command, ran = argv(timeout, text), options(timeout, text)
    logger.debug("asking cvc5 %s about:\n%s", command, text)
    # its own clock, apart from the one the limit is read on
    started = perf_counter()
    try:
        finished = subprocess.run(
            command,
            input=text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout + GRACE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("pyct stopped cvc5, which ran past its time limit")
        took(Given(text, ran, answered(None, Timeout()), perf_counter() - started))
        return Timeout(), frozenset()
    answer = _read(finished.stdout, finished.stderr, written)
    heard = answered(finished.stdout, answer)
    took(Given(text, ran, heard, perf_counter() - started))
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer, core_of(finished.stdout, written) if isinstance(answer, Unsat) else frozenset()


def _read(stdout: str, stderr: str, written: Program) -> Answer:
    """What cvc5 said, a sat model named by the leaves.

    A sat model with a value line pyct cannot read, or a name the program
    did not declare, is an ``Unknown()``; any other reply is what
    ``replies.answer_of`` makes of it.
    """
    try:
        answer = answer_of(stdout, stderr)
        # cvc5 answered by the constants the program declared; the run reads leaves by name
        return Sat(written.read(answer.model)) if isinstance(answer, Sat) else answer
    except SolverAnswerError as error:
        logger.warning("%s", error)
        return Unknown()
