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


def solve(prefix: tuple[Branch, ...], leaves: Mapping[str, type], timeout: float | None) -> Answer:
    """The input that takes ``prefix``, if there is one. ``timeout`` is the seconds cvc5 gets.

    The formula goes in on stdin rather than a file, so a run leaves nothing
    behind on disk.

    What cvc5 did never raises here. A crash, a nonzero exit, or output pyct
    does not recognize comes back as ``Error(detail)``, so the run keeps the
    records it already has and says the solver failed. The one exception is
    a ``sat`` whose model has a value line pyct cannot read: that is
    ``SolverAnswerError``, because a half-read model would quietly hand the
    seed's values back as the solver's.
    """
    text = render(prefix, leaves)
    argv = _argv(timeout)
    logger.debug("asking cvc5 %s about:\n%s", argv, text)
    finished = subprocess.run(argv, input=text, capture_output=True, text=True, check=False)
    answer = _answer(finished.stdout, finished.stderr)
    if isinstance(answer, Error):
        logger.warning("cvc5 failed to answer: %s", answer.detail)
    else:
        logger.debug("cvc5 answered %s", type(answer).__name__)
    return answer


def _argv(timeout: float | None) -> list[str]:
    """The command. cvc5 counts its limit in milliseconds, and rounds up is the honest way."""
    argv = [str(locate()), *ARGUMENTS]
    if timeout is not None:
        argv.append(f"--tlimit={math.ceil(timeout * 1000)}")
    return argv


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
