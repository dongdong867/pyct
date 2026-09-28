"""One ``run()`` of a C-bound target inside a program of its own, as a guest.

``python -m tests.acceptance.guest_c_work TARGET`` runs the target once in this
process with a 0.1 s budget and prints one JSON line: the seconds the run took
and the seed's failure. This process never calls ``own_the_alarm``, so pyct's
deadline is a guest's here. It runs without coverage.py, since the deadline
raises inside the target.
"""

import json
import sys
import time

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.run.isolation import Isolation
from pyct.run.run import run
from pyct.run.target import load_target


def main(spec: str) -> None:
    target = load_target(spec)
    started = time.monotonic()
    result = run(
        target, {"x": 0}, limits=Limits(budget=Budget(0.1)), isolation=Isolation.IN_PROCESS
    )
    failure = result.records[0].failure
    print(json.dumps({"took": time.monotonic() - started, "kind": failure and failure.kind}))


if __name__ == "__main__":
    main(sys.argv[1])
