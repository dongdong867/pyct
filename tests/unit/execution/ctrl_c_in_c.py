"""A Ctrl-C and the deadline's alarm that both wait for one long C call to return.

``interrupted_call(name)`` calls a target of ``targets/isolate/long_sum.py``
through ``execute``, with its line tracer on and a deadline 0.05 s ahead, and
has another process send this one a SIGINT 0.15 s in. The call outlives both
by about half a second, so the two signals are handled together as it returns.
"""

import os
import subprocess
import time

from pyct.execution.execute import ExecutionContext, ExecutionResult, execute
from tests.acceptance.harness import REPO_ROOT

LONG_SUM = REPO_ROOT / "targets" / "isolate" / "long_sum.py"


def interrupted_call(name: str) -> ExecutionResult:
    """Run the target ``name`` under a deadline a Ctrl-C lands after, as a person presses one."""
    namespace: dict[str, object] = {}
    exec(compile(LONG_SUM.read_text(), str(LONG_SUM), "exec"), namespace)
    fn = namespace[name]
    assert callable(fn)
    ctx = ExecutionContext(fn=fn, file=str(LONG_SUM))
    subprocess.Popen(["sh", "-c", f"sleep 0.15; kill -INT {os.getpid()}"])
    return execute(ctx, {"x": 0}, time.monotonic() + 0.05)
