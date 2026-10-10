"""Acceptance tests for start-a-fresh-interpreter-that-cannot-be-shadowed, one per criterion.

Each runs pyct from a folder that holds a ``pyct/`` package of its own, which says ``SHADOW``
and raises when imported. A thread at pyct's startup, from a ``sitecustomize`` or from the
target's import, makes pyct start a fresh interpreter, which must run the pyct that started it.
"""

import json
from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.sweeping import row_named, sweep

SHADOW = (
    "import os, sys\n"
    "sys.stderr.write(f'SHADOW pyct imported in pid {os.getpid()}\\n')\n"
    'raise RuntimeError("the folder\'s own pyct package")\n'
)
FORKS = 'def f(x: int) -> str:\n    if x > 3:\n        return "big"\n    return "small"\n'
# a daemon thread that sleeps, as a host's instrumentation starts one
A_THREAD = (
    "import threading, time\nthreading.Thread(target=time.sleep, args=(5,), daemon=True).start()\n"
)
FRESH_INPUTS = "each input runs in a fresh interpreter, because pyct's process runs other threads"


def shadowed_folder(tmp_path: Path) -> Path:
    """A folder holding its own ``pyct/`` package, ``plain.py``, and ``threaded.py``."""
    folder = tmp_path / "proj"
    (folder / "pyct").mkdir(parents=True)
    (folder / "pyct" / "__init__.py").write_text(SHADOW)
    (folder / "plain.py").write_text(FORKS)
    (folder / "threaded.py").write_text(f"{A_THREAD}\n\n{FORKS}")
    return folder


def a_thread_at_startup(tmp_path: Path) -> dict[str, str]:
    """The variables that put a ``sitecustomize`` starting a thread on ``PYTHONPATH``."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(A_THREAD)
    return {"PYTHONPATH": str(site)}


# start-a-fresh-interpreter-that-cannot-be-shadowed-runs-a-sweep-entry-as-installed: the entry's
# pyct process starts fresh, on a path that holds the folder ahead of pyct
def test_runs_a_sweep_entry_as_installed(tmp_path: Path) -> None:
    folder = shadowed_folder(tmp_path)

    result = sweep("plain", "--budget", "5", cwd=folder, env=a_thread_at_startup(tmp_path))

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, "plain", "f")
    assert row["status"] == "ran", row
    run = row["run"]
    assert run["stopped"] == "no fork to flip", row
    key = str((folder / "plain.py").resolve())
    # every line: the inputs ran three and the import ran the `def`
    assert (len(run["covered"][key]), run["total"][key]) == (4, 4), row
    assert "SHADOW" not in result.stderr


# start-a-fresh-interpreter-that-cannot-be-shadowed-runs-each-input-as-installed: each input's
# interpreter starts fresh, on the run's path, which holds the folder first
def test_runs_each_input_as_installed(tmp_path: Path) -> None:
    folder = shadowed_folder(tmp_path)

    result = run_pyct("threaded::f", "--args", '{"x": 0}', "--budget", "10", cwd=folder)

    assert result.returncode == 0, result.stderr
    assert result.stderr.count(FRESH_INPUTS) == 1, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 2, result.stdout
    second = inputs[1]["args"]
    assert isinstance(second, dict) and second["x"] > 3, result.stdout
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
    assert "SHADOW" not in result.stderr


# start-a-fresh-interpreter-that-cannot-be-shadowed-runs-both-starts-as-installed: pyct's
# process and each of its inputs start fresh
def test_runs_both_starts_as_installed(tmp_path: Path) -> None:
    folder = shadowed_folder(tmp_path)

    result = sweep("threaded", "--budget", "5", cwd=folder, env=a_thread_at_startup(tmp_path))

    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, "threaded", "f")
    assert row["status"] == "ran", json.dumps(row)
    assert row["run"]["stopped"] == "no fork to flip", row
    assert "SHADOW" not in result.stderr
