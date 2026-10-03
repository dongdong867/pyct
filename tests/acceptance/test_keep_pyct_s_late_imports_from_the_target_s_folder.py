"""Acceptance tests for keep-pyct-s-late-imports-from-the-target-s-folder, one per criterion.

Each runs pyct from a folder that holds modules named as standard-library modules. Every run
leaves coverage.py out: its start-up imports much of the standard library before the folder
joins the import path, which would hide a module pyct imports late. The criterion
keeps-any-late-import-of-pyct-s-from-the-folder is in ``tests/unit/run/test_own_imports.py``.
"""

import subprocess
import sys
from pathlib import Path

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.sweeping import row_named, sweep
from tests.acceptance.test_keep_a_sweep_entry_s_folder_from_hiding_pyct_s_modules import (
    a_thread_at_startup,
    folder_of,
    plain_python,
    raising,
)

# a target whose inputs take each way an input can fail: a SyntaxError, which Python 3.14's
# traceback reads through difflib, another raise, sys.exit, os._exit and a kill
FAILS = (
    "import os\n"
    "import sys\n"
    "\n"
    "\n"
    "def f(x: int) -> int:\n"
    "    if x == 1:\n"
    '        compile("fro x import y", "<src>", "exec")\n'
    "    if x == 2:\n"
    '        raise ValueError("bad")\n'
    "    if x == 3:\n"
    "        sys.exit(3)\n"
    "    if x == 4:\n"
    "        os._exit(4)\n"
    "    if x == 5:\n"
    "        os.kill(os.getpid(), 9)\n"
    "    return x\n"
)
# plain Python's one line for the SyntaxError, as pyct writes a failure's detail
SYNTAX_ERROR_LINE = (
    "import traceback\n"
    "try:\n"
    '    compile("fro x import y", "<src>", "exec")\n'
    "except SyntaxError as error:\n"
    "    entries = traceback.format_exception_only(error)\n"
    "    parts = (part.strip() for entry in entries for part in entry.splitlines())\n"
    "    print(' '.join(part for part in parts if part))\n"
)
# a target that reads a SyntaxError's message itself, then forks on a mark of difflib, if one of
# its imports has imported it: Python 3.14's traceback does, and so gets the folder's
READS_ITS_OWN = (
    "import sys\n"
    "import traceback\n"
    "\n"
    "\n"
    "def f(x: int) -> str:\n"
    "    try:\n"
    '        compile("fro x import y", "<src>", "exec")\n'
    "    except SyntaxError as error:\n"
    "        traceback.format_exception_only(error)\n"
    '    if x > getattr(sys.modules.get("difflib"), "MARK", 3):\n'
    '        return "big"\n'
    '    return "small"\n'
)
# the idna codec's first use imports stringprep, from the folder under plain Python; each target
# forks on 7 when that import raised and on 3 when it did not, once through a str literal's method
# and once through a tracked str's, each of which pyct's core runs in the target's place
ENCODES = (
    "def mark(text: str) -> int:\n"
    "    try:\n"
    '        text.encode("idna")\n'
    "    except RuntimeError:\n"
    "        return 7\n"
    "    return 3\n"
    "\n"
    "\n"
    "def literal(x: int) -> str:\n"
    "    try:\n"
    '        "ab".encode("idna")\n'
    "    except RuntimeError:\n"
    "        limit = 7\n"
    "    else:\n"
    "        limit = 3\n"
    "    if x > limit:\n"
    '        return "big"\n'
    '    return "small"\n'
    "\n"
    "\n"
    "def tracked(s: str) -> str:\n"
    "    if len(s) > mark(s):\n"
    '        return "long"\n'
    '    return "short"\n'
)
FORKS = 'def f(x: int) -> str:\n    if x > 3:\n        return "big"\n    return "small"\n'


def run_from(folder: Path, spec: str) -> subprocess.CompletedProcess[str]:
    """``pyct run <spec> --args '{"x": 0}' --budget 10`` from ``folder``, unmeasured."""
    return run_pyct(spec, "--args", '{"x": 0}', "--budget", "10", cwd=folder, timeout=60)


def syntax_error_line() -> str:
    """Plain Python's one line for ``FAILS``'s SyntaxError, from a folder of no modules."""
    result = subprocess.run(
        [sys.executable, "-P", "-c", SYNTAX_ERROR_LINE],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def failure_by_x(stdout: str) -> dict[int, object]:
    """Each input's failure, by the ``x`` it ran with."""
    by_x: dict[int, object] = {}
    for line in input_lines(stdout):
        args = line["args"]
        assert isinstance(args, dict), line
        x = args["x"]
        assert isinstance(x, int), line
        by_x[x] = line["failure"]
    return by_x


# keep-pyct-s-late-imports-from-the-target-s-folder-reads-each-failure-past-every-stdlib-name
def test_reads_each_failure_past_every_stdlib_name(tmp_path: Path) -> None:
    shadows = {f"{name}.py": raising(name) for name in sys.stdlib_module_names}
    folder = folder_of(tmp_path, {**shadows, "fails.py": FAILS})

    ran = run_from(folder, "fails::f")
    fresh = sweep(
        "fails", "--budget", "10", cwd=folder, env=a_thread_at_startup(tmp_path), measured=False
    )

    assert ran.returncode == 0, ran.stderr
    failures = failure_by_x(ran.stdout)
    assert len(input_lines(ran.stdout)) == 6, ran.stdout
    assert sorted(failures) == [0, 1, 2, 3, 4, 5], ran.stdout
    assert failures[0] is None
    assert all(failures[x] is not None for x in range(1, 6)), failures
    assert failures[1] == {"kind": "target_raised", "detail": syntax_error_line()}
    assert summary_line(ran.stdout)["stopped"] == "no fork to flip"
    assert fresh.returncode == 0, fresh.stderr
    assert row_named(fresh.stdout, "fails", "f")["status"] == "ran", fresh.stdout
    for result in (ran, fresh):
        assert "SHADOW" not in result.stderr, result.stderr


# keep-pyct-s-late-imports-from-the-target-s-folder-lets-the-target-read-its-own-syntax-error
def test_lets_the_target_read_its_own_syntax_error(tmp_path: Path) -> None:
    folder = folder_of(tmp_path, {"difflib.py": "MARK = 7\n", "reads.py": READS_ITS_OWN})
    plain = plain_python(
        folder,
        "import reads; reads.f(0); print(getattr(sys.modules.get('difflib'), 'MARK', 3))",
    )

    ran = run_from(folder, "reads::f")

    assert plain.returncode == 0, plain.stderr
    mark = int(plain.stdout)
    assert ran.returncode == 0, ran.stderr
    forks = input_lines(ran.stdout)[0]["forks"]
    assert isinstance(forks, list), ran.stdout
    assert [fork["expression"] for fork in forks] == [[">", "x", mark]], forks
    assert summary_line(ran.stdout)["stopped"] == "no fork to flip", ran.stdout


# keep-pyct-s-late-imports-from-the-target-s-folder-runs-a-target-named-as-a-stdlib-module
def test_runs_a_target_named_as_a_stdlib_module(tmp_path: Path) -> None:
    folder = folder_of(tmp_path, {"colorsys.py": FORKS})
    plain = plain_python(folder, "import colorsys; print(colorsys.f(0), colorsys.f(4))")

    ran = run_from(folder, "colorsys::f")

    assert plain.stdout == "small big\n", plain.stderr
    assert ran.returncode == 0, ran.stderr
    inputs = input_lines(ran.stdout)
    assert [line["failure"] for line in inputs] == [None, None], ran.stdout
    forks = inputs[0]["forks"]
    assert isinstance(forks, list), ran.stdout
    assert [fork["expression"] for fork in forks] == [[">", "x", 3]], forks


# keep-pyct-s-late-imports-from-the-target-s-folder-lets-the-target-import-its-own-sysconfig
def test_lets_the_target_import_its_own_sysconfig(tmp_path: Path) -> None:
    uses = FORKS.replace("x > 3", "x > sysconfig.MARK")
    folder = folder_of(
        tmp_path, {"sysconfig.py": "MARK = 7\n", "usesc.py": f"import sysconfig\n\n\n{uses}"}
    )
    plain = plain_python(folder, "import usesc; print(usesc.f(0), usesc.f(8))")

    ran = run_from(folder, "usesc::f")

    assert plain.stdout == "small big\n", plain.stderr
    assert ran.returncode == 0, ran.stderr
    inputs = input_lines(ran.stdout)
    assert [line["failure"] for line in inputs] == [None, None], ran.stdout
    forks = inputs[0]["forks"]
    assert isinstance(forks, list), ran.stdout
    assert [fork["expression"] for fork in forks] == [[">", "x", 7]], forks


# keep-pyct-s-late-imports-from-the-target-s-folder-lets-a-str-method-import-from-the-folder
def test_lets_a_str_method_import_from_the_folder(tmp_path: Path) -> None:
    folder = folder_of(tmp_path, {"stringprep.py": raising("stringprep"), "enc.py": ENCODES})
    plain = plain_python(folder, "import enc; print(enc.mark('ab'))")

    literal = run_from(folder, "enc::literal")
    tracked = run_pyct(
        "enc::tracked", "--args", '{"s": "ab"}', "--budget", "10", cwd=folder, timeout=60
    )

    assert plain.returncode == 0, plain.stderr
    mark = int(plain.stdout)
    for ran, subject in ((literal, "x"), (tracked, ["len", "s"])):
        assert ran.returncode == 0, ran.stderr
        forks = input_lines(ran.stdout)[0]["forks"]
        assert isinstance(forks, list), ran.stdout
        assert [fork["expression"] for fork in forks] == [[">", subject, mark]], forks
        assert "SHADOW stringprep" in ran.stderr, ran.stderr
