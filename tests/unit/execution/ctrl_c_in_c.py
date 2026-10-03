"""A Ctrl-C and the deadline's alarm that both wait for one long C call to return.

``interrupted_call(name)`` calls a target of ``targets/isolate/long_sum.py``
through ``execute``, with its line tracer on and a deadline 0.05 s ahead, and
has another process send this one a SIGINT 0.15 s in. The call outlives both,
and returns more than ``_HOLD_AT_MOST`` past the deadline on every supported
Python, so the two signals are handled together as it returns, after the
alarm's hold would have run out had it counted from the deadline.

``spin_in_pyct`` is a loop whose code pyct's package holds, as a core
operation's is, so an alarm can land in pyct's own frames, where it is held
briefly and owes nothing.
"""

import os
import subprocess
import time
from collections.abc import Callable

from pyct.core.branch import PYCT_DIR
from pyct.execution.execute import ExecutionContext, execute
from tests.acceptance.harness import REPO_ROOT

LONG_SUM = REPO_ROOT / "targets" / "isolate" / "long_sum.py"


def spin_until(instant: float) -> None:
    """Spin until the monotonic ``instant``, in a frame of its own, as pyct calls the target.

    From 3.13 a signal handled at a loop's backward jump can raise from an
    offset outside the frame's exception table, so the ``with``, ``finally``
    or ``except`` around the loop is skipped, and an ``except`` body leaves
    its exception set for the thread. A loop in a frame of its own keeps
    the caller's ``with``, ``try`` and ``except`` out of that.
    """
    while time.monotonic() < instant:
        pass


def interrupted_call(name: str) -> float:
    """Run the target ``name`` under a deadline a Ctrl-C lands after, as a person presses one.

    Returns how far past the deadline the call returned, when it did.
    """
    namespace: dict[str, object] = {}
    exec(compile(LONG_SUM.read_text(), str(LONG_SUM), "exec"), namespace)
    fn = namespace[name]
    assert callable(fn)
    ctx = ExecutionContext(fn=fn, file=str(LONG_SUM))
    subprocess.Popen(["sh", "-c", f"sleep 0.15; kill -INT {os.getpid()}"])
    at = time.monotonic() + 0.05
    execute(ctx, {"x": 0}, at)
    return time.monotonic() - at


_SPIN = """\
import time


def spin(until, owner=None):
    while time.monotonic() < until and (owner is None or owner.hold.brief is None):
        pass
"""


def spin_in_pyct() -> Callable[..., object]:
    """A loop compiled as a file in pyct's package: ``spin(until, owner=None)``.

    It runs until the monotonic instant ``until``, or, given the owned
    deadline's state, until the alarm was held briefly once. It calls
    no Python function, so an alarm lands in its own frame.
    """
    namespace: dict[str, object] = {}
    exec(compile(_SPIN, f"{PYCT_DIR}core/spin.py", "exec"), namespace)
    spin = namespace["spin"]
    assert callable(spin)
    return spin
