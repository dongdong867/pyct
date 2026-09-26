"""Ask cvc5 whether a path can be taken, and for an input that takes it."""

import logging
import math
import subprocess
from collections.abc import Mapping

from pyct.core.branch import Branch
from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat, model_from
from pyct.solver.locate import locate
from pyct.solver.render import render

logger = logging.getLogger(__name__)

# read one SMT-LIB program from stdin, print a model with the answer, say nothing else
ARGUMENTS = ("--produce-models", "--lang", "smt", "--quiet")

# cvc5 stops itself at --tlimit; pyct stops it this much later when it does not
GRACE_SECONDS = 1.0

# the longest wait Python's poll takes, 2**31 - 1 milliseconds, in whole seconds
LONGEST_WAIT_SECONDS = 2_147_483.0


def solve(prefix: tuple[Branch, ...], leaves: Mapping[str, type], timeout: float) -> Answer:
    """The input that takes ``prefix``, if there is one. ``timeout`` is the seconds cvc5 gets.

    The formula goes in on stdin rather than a file, so a run leaves nothing
    behind on disk.

    ``timeout`` is finite and above zero, and cvc5 is told it as its limit. A
    cvc5 still running ``GRACE_SECONDS`` past it is stopped by pyct, and that
    is a ``Timeout()`` as well, so every solve ends near its limit. A limit
    longer than Python can wait, about 24 days, is cut to what it can.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. The one exception is
    a ``sat`` whose model has a value line pyct cannot read: that is
    ``SolverAnswerError``, because a half-read model would quietly hand the
    seed's values back as the solver's.
    """
    text = render(prefix, leaves)
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
        logger.warning("pyct stopped cvc5 after %g s, past its time limit", timeout + GRACE_SECONDS)
        return Timeout()
    answer = _answer(finished.stdout, finished.stderr)
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer


def _argv(timeout: float) -> list[str]:
    """The command. cvc5 counts its limit in milliseconds, and rounds up is the honest way.

    Rounding up also keeps any limit above zero at 1 or more, since cvc5
    reads ``--tlimit=0`` as no limit.
    """
    return [str(locate()), *ARGUMENTS, f"--tlimit={math.ceil(timeout * 1000)}"]


def _answer(stdout: str, stderr: str) -> Answer:
    """What cvc5 said. The first word decides; anything unrecognized is kept whole."""
    lines = stdout.strip().splitlines()
    head = lines[0] if lines else ""
    if head == "sat":
        return Sat(model_from(lines[1:]))
    if head == "unsat":
        return Unsat()
    if head == "unknown":
        return Unknown()
    if not lines and "timeout" in stderr:
        return Timeout()
    return Error(f"{stdout}\n{stderr}".strip())
