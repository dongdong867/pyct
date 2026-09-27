"""The budget: with every module unchanged since pyct substituted it, an import costs at most
25% more than Python's own import of the package as written.

A generated package of 200 modules, each with the compares pyct substitutes, is imported in
fresh interpreters: as written, from the bytecode Python keeps, and substituted, from pyct's
cache. Each takes its best of five, so a slow moment of the machine counts against neither.
The files are left to settle first, as a package on disk has, so the cache trusts their stat.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from tests.acceptance.harness import COVERAGE_STARTUP

MODULES = 200
BUDGET = 1.25

# one module: twenty functions, each with an `in` on a set, an `is True` and an `in` on a string
MODULE = "\n".join(
    f"def f{n}(x, s):\n"
    f"    if x in {{1, 2, {n}}}:\n"
    "        return 'a'\n"
    f"    if (x > {n}) is True and s not in 'abc':\n"
    "        return 'b'\n"
    "    return [y for y in range(x) if y in (1, 2)]\n"
    for n in range(20)
)

# the import, timed alone in a fresh interpreter, as written or substituted
TIMED = """
import sys, time
from pathlib import Path
sys.path.insert(0, ".")
from pyct.intercept.hook import Interception, intercepting
mode, cache = sys.argv[1], sys.argv[2]
start = time.perf_counter()
if mode == "written":
    import generated
else:
    with intercepting(Interception(module="generated", cache=Path(cache))):
        import generated
print(time.perf_counter() - start)
"""


def imported(folder: Path, mode: str) -> float:
    """How long one import of the package took in a fresh interpreter, in seconds."""
    environment = {k: v for k, v in os.environ.items() if k not in COVERAGE_STARTUP}
    finished = subprocess.run(
        [sys.executable, "-c", TIMED, mode, str(folder / "cache")],
        cwd=folder,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return float(finished.stdout)


def test_a_warm_substituted_import_costs_at_most_a_quarter_more(tmp_path: Path) -> None:
    package = tmp_path / "generated"
    package.mkdir()
    lines = [f"from generated import m{n}" for n in range(MODULES)]
    (package / "__init__.py").write_text("\n".join(lines) + "\n")
    for n in range(MODULES):
        (package / f"m{n}.py").write_text(MODULE)
    written_at = time.monotonic()
    # the first of each writes Python's bytecode and pyct's cache
    imported(tmp_path, "written")
    imported(tmp_path, "substituted")
    time.sleep(max(0.0, written_at + 2.5 - time.monotonic()))
    imported(tmp_path, "substituted")

    written = min(imported(tmp_path, "written") for _ in range(5))
    substituted = min(imported(tmp_path, "substituted") for _ in range(5))

    assert substituted <= BUDGET * written, (substituted, written)
