"""The budget: with every module unchanged since pyct substituted it, an import costs at most
25% more than Python's own import of the package as written, or 1 ms more, whichever is more.

The 1 ms is pyct's own fixed cost, which a package that imports in a few milliseconds would
otherwise cross. A generated package of 200 modules, and one of 3, each module with every shape
pyct substitutes, is imported in
fresh interpreters: as written, from the bytecode Python keeps, and substituted, from pyct's
cache. Each takes its best of nine, run in alternating pairs, so a slow moment of the machine
counts against neither.
The files are left to settle first, as a package on disk has, so the cache trusts their stat.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.acceptance.harness import COVERAGE_STARTUP

# what substitution may add to a warm import: a quarter of it, or pyct's fixed cost in seconds
SHARE = 0.25
FIXED = 0.001

# one module: twenty functions, each with every shape pyct substitutes, an `in` on a set, an
# `is True`, an `in` on a string, conversions, a str literal's method and a float literal on the
# left of an operator, beside plain code of the same kinds that stays as written
MODULE = "\n".join(
    f"def f{n}(x, s, y):\n"
    f"    if x in {{1, 2, {n}}}:\n"
    "        return 'a'\n"
    f"    if (x > {n}) is True and s not in 'abc':\n"
    "        return 'b'\n"
    "    if int(s) + float(x) > 2.5 * x and bool(y) and 'abc'.find(s) > 0:\n"
    "        return x * y + x / y - s.replace('a', 'b').count('c')\n"
    "    if x < y and s.startswith('ab'):\n"
    "        return list(map(int, s.split(',')))\n"
    "    return [z for z in range(x) if z in (1, 2)]\n"
    for n in range(20)
)

# the import, timed alone in a fresh interpreter, as written or substituted
TIMED = """
import gc, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from pyct.intercept.hook import Interception, intercepting
mode, cache = sys.argv[1], sys.argv[2]
# a collection now, so the objects pyct's own imports made do not set when one falls inside
# the timed import
gc.collect()
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


def allowed(written: float) -> float:
    """How long a substituted import may take, given how long the import as written took."""
    return written + max(SHARE * written, FIXED)


def test_the_allowance_is_a_quarter_or_the_fixed_cost_whichever_is_more() -> None:
    assert allowed(0.012) == 0.012 + 0.003
    assert allowed(0.002) == 0.002 + 0.001


@pytest.mark.serial
@pytest.mark.parametrize("modules", [200, 3])
def test_a_warm_substituted_import_costs_at_most_a_quarter_or_1_ms_more(
    tmp_path: Path, modules: int
) -> None:
    package = tmp_path / "generated"
    package.mkdir()
    lines = [f"from generated import m{n}" for n in range(modules)]
    (package / "__init__.py").write_text("\n".join(lines) + "\n")
    for n in range(modules):
        (package / f"m{n}.py").write_text(MODULE)
    written_at = time.monotonic()
    # the first of each writes Python's bytecode and pyct's cache
    imported(tmp_path, "written")
    imported(tmp_path, "substituted")
    time.sleep(max(0.0, written_at + 2.5 - time.monotonic()))
    imported(tmp_path, "substituted")

    # pair by pair, so a slow moment of the machine lands on both sides alike
    pairs = [(imported(tmp_path, "written"), imported(tmp_path, "substituted")) for _ in range(9)]
    written = min(first for first, _ in pairs)
    substituted = min(second for _, second in pairs)

    assert substituted <= allowed(written), (substituted, written)
