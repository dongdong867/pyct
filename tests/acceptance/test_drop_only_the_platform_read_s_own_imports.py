"""Acceptance tests for drop-only-the-platform-read-s-own-imports, one per criterion.

The criterion keeps-another-thread-s-finished-import is in ``tests/unit/run/test_run_platform.py``:
a thread's import that starts and ends within the read's 12 ms or so cannot be timed from outside.
"""

import subprocess
import sys
from pathlib import Path

from tests.acceptance.harness import summary_line
from tests.acceptance.sweeping import environment

FORKS = 'def f(x: int) -> str:\n    if x > 3:\n        return "big"\n    return "small"\n'
# how many modules the host's thread imports, one after another, each in about 5 ms: more than
# the second and a half they take covers pyct's start, platform read included, in each process
STREAMED = 300
# a host's instrumentation: a thread, started as Python starts, that imports one module after
# another while pyct's modules import and the platform is read, and then says whether each import
# went through and each module is still the one it got
IMPORTS_ALONG = (
    "import importlib, sys, threading\n"
    "def load():\n"
    "    try:\n"
    f"        held = [importlib.import_module(f'streamed{{n}}') for n in range({STREAMED})]\n"
    "    except BaseException as error:\n"
    "        sys.stderr.write(f'THREAD {error!r}\\n')\n"
    "        return\n"
    "    lost = [each.__name__ for each in held if sys.modules.get(each.__name__) is not each]\n"
    "    sys.stderr.write(f'THREAD lost {lost}\\n' if lost else 'KEPT every module\\n')\n"
    "threading.Thread(target=load).start()\n"
)


# drop-only-the-platform-read-s-own-imports-keeps-another-thread-s-import-in-progress
def test_keeps_another_thread_s_import_in_progress(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(IMPORTS_ALONG)
    for n in range(STREAMED):
        (site / f"streamed{n}.py").write_text("import time\ntime.sleep(0.005)\n")
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "plain.py").write_text(FORKS)

    ran = subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", "plain::f", "--args", '{"x": 0}'],
        cwd=folder,
        env=environment({"PYTHONPATH": str(site)}, measured=False),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert ran.returncode == 0, ran.stderr
    assert summary_line(ran.stdout)["stopped"] == "no fork to flip", ran.stdout
    assert "THREAD" not in ran.stderr, ran.stderr
    assert "KEPT every module" in ran.stderr, ran.stderr
