"""Acceptance tests for keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules, one per criterion.

Each runs pyct from a folder that holds modules named as standard-library modules, each of which
says ``SHADOW`` and raises when imported. pyct's own imports must never reach them. Every sweep
leaves coverage.py out: its start-up imports much of the standard library before the folder joins
the import path, which would hide a module pyct imports late.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.sweeping import environment, row_named, sweep

FORKS = 'def f(x: int) -> str:\n    if x > 3:\n        return "big"\n    return "small"\n'
# a daemon thread that sleeps, as a host's instrumentation starts one
A_THREAD = (
    "import threading, time\nthreading.Thread(target=time.sleep, args=(5,), daemon=True).start()\n"
)
# plain Python, started with -P, puts the folder first on its path and then runs one of these
PLAIN_PYTHON = "import sys, os; sys.path.insert(0, os.getcwd())\n"
CALLS_PLAIN = "import plain; print(plain.f(0), plain.f(4))"
IMPORTS_USESCOLOR = (
    "try:\n    import usescolor\nexcept RuntimeError as error:\n    print(repr(error))"
)


def raising(name: str) -> str:
    """The source of a module named ``name`` that says ``SHADOW <name>`` and raises."""
    return (
        f"import sys\nsys.stderr.write('SHADOW {name}\\n')\nraise RuntimeError('folder {name}')\n"
    )


def folder_of(tmp_path: Path, files: dict[str, str]) -> Path:
    """A folder ``proj`` holding each of ``files``, by name and source."""
    folder = tmp_path / "proj"
    folder.mkdir()
    for name, source in files.items():
        (folder / name).write_text(source)
    return folder


def a_thread_at_startup(tmp_path: Path) -> dict[str, str]:
    """The variables that put a ``sitecustomize`` starting a thread on ``PYTHONPATH``."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(A_THREAD)
    return {"PYTHONPATH": str(site)}


def plain_python(folder: Path, code: str) -> subprocess.CompletedProcess[str]:
    """Plain Python, started with ``-P`` from ``folder``, running ``code`` with the folder first on
    its path."""
    return subprocess.run(
        [sys.executable, "-P", "-c", PLAIN_PYTHON + code],
        cwd=folder,
        # unmeasured: coverage.py's start-up would import datetime and more ahead of the folder
        env=environment(measured=False),
        capture_output=True,
        text=True,
        check=False,
    )


def sweep_from(
    folder: Path, module: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """``pyct sweep <module> --budget 5`` from ``folder``, unmeasured, and the result."""
    return sweep(module, "--budget", "5", cwd=folder, env=env, measured=False)


def ran_to_the_end(result: subprocess.CompletedProcess[str], module: str) -> dict[str, Any]:
    """The run of ``<module>::f``'s row, once the sweep exited 0 and the row ran to its end."""
    assert result.returncode == 0, result.stderr
    row = row_named(result.stdout, module, "f")
    assert row["status"] == "ran", row
    assert row["run"]["stopped"] == "no fork to flip", row
    return row["run"]


# keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-sweeps-past-a-folder-json
def test_sweeps_past_a_folder_json(tmp_path: Path) -> None:
    folder = folder_of(tmp_path, {"plain.py": FORKS, "json.py": raising("json")})

    result = sweep_from(folder, "plain")
    ran = run_pyct("plain::f", "--args", '{"x": 0}', "--budget", "5", cwd=folder)

    run = ran_to_the_end(result, "plain")
    assert ran.returncode == 0, ran.stderr
    alone = summary_line(ran.stdout)
    for key in ("covered", "total", "uncovered"):
        assert run[key] == alone[key], (key, run, alone)
    assert "SHADOW" not in result.stderr


# keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-sweeps-past-it-when-started-fresh
def test_sweeps_past_it_when_started_fresh(tmp_path: Path) -> None:
    # argparse, since the fresh boot imports json itself before any path changes
    folder = folder_of(tmp_path, {"plain.py": FORKS, "argparse.py": raising("argparse")})

    result = sweep_from(folder, "plain", env=a_thread_at_startup(tmp_path))

    ran_to_the_end(result, "plain")
    assert "SHADOW" not in result.stderr


# keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-runs-past-every-stdlib-name
def test_runs_past_every_stdlib_name(tmp_path: Path) -> None:
    shadows = {f"{name}.py": raising(name) for name in sys.stdlib_module_names}
    folder = folder_of(tmp_path, {**shadows, "plain.py": FORKS})
    plain = plain_python(folder, CALLS_PLAIN)
    assert (plain.returncode, plain.stdout) == (0, "small big\n"), plain.stderr

    ran = run_pyct("plain::f", "--args", '{"x": 0}', "--budget", "5", cwd=folder)
    forked = sweep_from(folder, "plain")
    fresh = sweep_from(folder, "plain", env=a_thread_at_startup(tmp_path))

    assert ran.returncode == 0, ran.stderr
    assert len(input_lines(ran.stdout)) == 2, ran.stdout
    assert summary_line(ran.stdout)["stopped"] == "no fork to flip"
    ran_to_the_end(forked, "plain")
    ran_to_the_end(fresh, "plain")
    for result in (ran, forked, fresh):
        assert "SHADOW" not in result.stderr, result.stderr


# keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-lets-the-target-import-its-own
def test_lets_the_target_import_its_own(tmp_path: Path) -> None:
    uses = FORKS.replace("x > 3", "x > helper.LIMIT")
    folder = folder_of(
        tmp_path, {"helper.py": "LIMIT = 7\n", "uses.py": f"import helper\n\n\n{uses}"}
    )

    result = sweep_from(folder, "uses")
    ran = run_pyct("uses::f", "--args", '{"x": 0}', "--budget", "5", cwd=folder)

    run = ran_to_the_end(result, "uses")
    assert ran.returncode == 0, ran.stderr
    forks = input_lines(ran.stdout)[0]["forks"]
    assert isinstance(forks, list), ran.stdout
    assert [fork["expression"] for fork in forks] == [[">", "x", 7]], forks
    key = str((folder / "uses.py").resolve())
    under_the_if = 6
    assert under_the_if in run["covered"][key], run
    assert run["covered"] == summary_line(ran.stdout)["covered"], ran.stdout


# keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-lets-the-target-import-its-own, for a
# module named as one pyct's platform read imports on macOS
def test_lets_the_target_import_its_own_datetime(tmp_path: Path) -> None:
    uses = FORKS.replace("x > 3", "x > datetime.MARK")
    folder = folder_of(
        tmp_path, {"datetime.py": "MARK = 7\n", "usesdt.py": f"import datetime\n\n\n{uses}"}
    )
    plain = plain_python(folder, "import usesdt; print(usesdt.f(0), usesdt.f(8))")

    ran = run_pyct("usesdt::f", "--args", '{"x": 0}', "--budget", "5", cwd=folder)
    result = sweep_from(folder, "usesdt")

    assert plain.stdout == "small big\n", plain.stderr
    assert ran.returncode == 0, ran.stderr
    inputs = input_lines(ran.stdout)
    assert [line["failure"] for line in inputs] == [None, None], ran.stdout
    forks = inputs[0]["forks"]
    assert isinstance(forks, list), ran.stdout
    assert [fork["expression"] for fork in forks] == [[">", "x", 7]], forks
    alone = summary_line(ran.stdout)
    assert alone["stopped"] == "no fork to flip", ran.stdout
    assert ran_to_the_end(result, "usesdt")["covered"] == alone["covered"], result.stdout


# the criterion keep-a-sweep-entry-s-folder-from-hiding-pyct-s-modules-
# fails-a-target-that-imports-a-raising-module, its id split over two lines
def test_fails_a_target_that_imports_a_raising_module(tmp_path: Path) -> None:
    usescolor = "import colorsys\n\n\ndef f(x: int) -> int:\n    return x\n"
    folder = folder_of(tmp_path, {"colorsys.py": raising("colorsys"), "usescolor.py": usescolor})
    plain = plain_python(folder, IMPORTS_USESCOLOR)

    ran = run_pyct("usescolor::f", "--args", '{"x": 0}', cwd=folder)
    swept = sweep_from(folder, "usescolor")

    assert plain.stdout == "RuntimeError('folder colorsys')\n", plain.stderr
    for result in (ran, swept):
        assert result.returncode == 1, result.stderr
        # the folder's colorsys writes its own line as it imports, as it does under plain Python
        own = [line for line in result.stderr.splitlines() if line != "SHADOW colorsys"]
        assert own == [f"cannot import usescolor: {plain.stdout.strip()}"], result.stderr
