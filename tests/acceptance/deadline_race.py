"""Runs that end as their deadline or pyct's kill comes, again and again, in a process of their own.

``python -m tests.acceptance.deadline_race CASE SECONDS`` makes ``run()`` calls for
SECONDS and prints one JSON line: how many seeds returned and timed out, the
records that ended otherwise, and how often SIGALRM's own handler ran. Each run
sets the target's time from how the one before ended, a step longer after a
return and a step shorter after a timeout, so the calls keep ending within a
step of the instant they race, with a little noise so each lands elsewhere.

The process keeps SIG_DFL as SIGALRM's handler, or its own counting handler for
the ``counted`` case: a SIGALRM of pyct's that reached it would end the process
or be counted. The ``owned`` case gives SIGALRM to pyct first, as the command
line does, so its in-process calls take the kernel timer instead of a watcher.
It runs without coverage.py, since the deadline raises inside the target.
"""

import json
import random
import signal
import sys
import time
import types
from dataclasses import dataclass

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.execution.deadline import own_the_alarm
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import RunResult
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from targets.isolate import spins

TIMEOUT = Failure(kind=FailureKind.TIMEOUT, detail="deadline passed")


@dataclass(frozen=True)
class Case:
    """One criterion's runs: the target, where its inputs run, the budget, and the time it races.

    ``start`` is the target's first time, ``step`` how far each run moves it.
    """

    target: str
    isolation: Isolation
    budget: float
    start: float
    step: float


CASES = {
    "in-process": Case("spin", Isolation.IN_PROCESS, 0.002, 0.006, 50e-6),
    "counted": Case("spin", Isolation.IN_PROCESS, 0.002, 0.006, 50e-6),
    "owned": Case("spin", Isolation.IN_PROCESS, 0.002, 0.006, 50e-6),
    "forked": Case("spin", Isolation.AUTO, 0.02, 0.02, 50e-6),
    "past-the-kill": Case("outlive", Isolation.AUTO, 0.05, 0.55, 0.002),
}

# how many runs went through SIGALRM's own handler, in the counted case
counted = [0]


def count(number: int, frame: types.FrameType | None) -> None:
    counted[0] += 1


def main(name: str, seconds: float) -> None:
    case = CASES[name]
    handler = count if name == "counted" else signal.SIG_DFL
    signal.signal(signal.SIGALRM, handler)
    if name == "owned":
        # as the command line does: the process is pyct's, and SIGALRM its deadline's for good
        own_the_alarm()
        handler = signal.getsignal(signal.SIGALRM)
    target = load_target(f"targets.isolate.spins::{case.target}")
    limits = Limits(budget=Budget(case.budget))
    tally = {"returned": 0, "timeout": 0, "bad": [], "handler_moved": 0}
    at = case.start
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        spins.SECONDS = max(at + random.uniform(-case.step, case.step), 0.0)
        result = run(target, {}, limits=limits, isolation=case.isolation)
        returned = _tally(result, tally)
        at += case.step if returned else -case.step
        tally["handler_moved"] += signal.getsignal(signal.SIGALRM) is not handler
    tally["counted"] = counted[0]
    print(json.dumps(tally))


def _tally(result: RunResult, tally: dict) -> bool:
    """Count the seed's ending, keep every record that ended otherwise, and say if it returned."""
    for record in result.records:
        failure = record.failure
        if failure is not None and failure != TIMEOUT:
            tally["bad"].append(repr(failure))
    seed = result.records[0].failure
    tally["returned" if seed is None else "timeout"] += 1
    return seed is None


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))
