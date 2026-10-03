"""A program that calls ``run()`` under a Python-level tracer of its own, in a process of its own.

``python -m tests.acceptance.traced_guest TRACER NAME TRIES INTERRUPT`` installs a SIGALRM
handler of its own, then, TRIES times, installs ``TRACER`` (``none``, ``settrace`` or
``monitoring``, from ``targets/isolate/traced.py``) and calls ``run()`` on that module's
``NAME`` with ``Isolation.IN_PROCESS``. With INTERRUPT ``yes`` it has another process send it a
SIGINT 0.3 s after the call's C call began, past the run's 0.1 s budget; otherwise the budget
is 1 s. It prints one JSON line per try: how the run ended, ``KeyboardInterrupt`` or the seed's
failure kind and detail, the seconds ``run()`` took, and whether SIGALRM's handler was the
program's own afterward. It runs without coverage.py, since the deadline raises in the tracer.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target
from targets.isolate import traced

# how long after the C call began the SIGINT comes: past the 0.1 s budget, inside the call
SIGINT_AFTER = 0.3


def _own(signal_number: int, frame: types.FrameType | None) -> None:
    """The program's own SIGALRM handler, which run() borrows and must give back."""


def _send_sigint_once_calling(calling: Path) -> subprocess.Popen[bytes]:
    """Have another process send this one a SIGINT ``SIGINT_AFTER`` after ``calling`` exists.

    It looks for the file for at most 20 seconds, and the try kills it once it is done.
    """
    script = (
        f'n=0; while [ ! -e "{calling}" ] && [ $n -lt 2000 ]; do sleep 0.01; n=$((n+1)); done; '
        f'[ -e "{calling}" ] && sleep {SIGINT_AFTER} && kill -INT {os.getpid()}'
    )
    return subprocess.Popen(["sh", "-c", script])


def one_try(tracer: str, name: str, interrupt: bool, calling: Path) -> dict[str, object]:
    """One run() of ``name`` under ``tracer``, with its SIGINT's sender, if any, ended after."""
    calling.unlink(missing_ok=True)
    sender = _send_sigint_once_calling(calling) if interrupt else None
    try:
        return _ran(tracer, name, interrupt)
    finally:
        if sender is not None:
            sender.kill()
            sender.wait()


def _ran(tracer: str, name: str, interrupt: bool) -> dict[str, object]:
    """One run() of ``name`` under ``tracer``, and how it ended."""
    target = load_target(f"targets.isolate.traced::{name}")
    limits = Limits(budget=Budget(seconds=0.1 if interrupt else 1.0))
    traced.install(tracer)
    started = time.monotonic()
    try:
        result = run(target, {"x": 0}, limits=limits, isolation=Isolation.IN_PROCESS)
        failure = result.records[0].failure
        ended = None if failure is None else [failure.kind.value, failure.detail]
    except KeyboardInterrupt:
        ended = "KeyboardInterrupt"
    took = time.monotonic() - started
    sys.settrace(None)
    own = signal.getsignal(signal.SIGALRM) is _own
    return {"ended": ended, "took": took, "own_handler": own}


def main() -> None:
    tracer, name, tries, interrupt = sys.argv[1:5]
    signal.signal(signal.SIGALRM, _own)
    with tempfile.TemporaryDirectory() as scratch:
        calling = Path(scratch) / "calling"
        os.environ["PYCT_TEST_CALLING"] = str(calling)
        for _ in range(int(tries)):
            print(json.dumps(one_try(tracer, name, interrupt == "yes", calling)), flush=True)


if __name__ == "__main__":
    main()
