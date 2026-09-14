"""What every acceptance test needs: spawn pyct, run it in process, read its stdout.

The subprocess runs ``python -P -m pyct`` from the repository root with
``PYTHONPATH`` removed, so a test proves the target imports from the working
directory rather than from an inherited path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# what the crashing cvc5 says before it dies, so a test can pin how pyct passes it on
CRASH_DETAIL = "cvc5: Fatal failure within the solver"


def run_pyct(*argv: str, path: str | None = None) -> subprocess.CompletedProcess[str]:
    """Spawn ``pyct run`` with the given argv. ``path`` replaces the child's ``PATH``."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # the timeout test spawns a target that never returns, so a broken
        # budget has to fail the test instead of hanging the suite
        timeout=30,
    )


def let_pyct_run_in_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put this interpreter where a fresh one would be, and undo it after the test.

    ``load_target`` inserts the working directory on ``sys.path`` and leaves the
    imported target in ``sys.modules``; both are restored so the subprocess tests
    around this one keep proving what they prove.
    """
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setattr(sys, "path", list(sys.path))
    for name in [n for n in sys.modules if n.split(".", 1)[0] == "targets"]:
        monkeypatch.delitem(sys.modules, name)


def crashing_cvc5(tmp_path: Path) -> Path:
    """A cvc5 that reads the formula and dies instead of answering, for ``run_pyct(path=...)``.

    It fails ``--version`` the same way, so a run pointed at it has no version
    to report either.
    """
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        "cat > /dev/null\n"
        f"echo '{CRASH_DETAIL}' >&2\n"
        "exit 1\n"
    )
    script.chmod(0o755)
    return script


def input_lines(stdout: str) -> list[dict[str, object]]:
    """The one line per input, without the summary line that closes stdout.

    A tool tells the summary from an input line by its ``stopped`` key, and
    that is how this tells them apart too: a stdout with no such last line is
    all input lines.
    """
    lines = [json.loads(line) for line in stdout.splitlines()]
    return lines[:-1] if lines and "stopped" in lines[-1] else lines


def summary_line(stdout: str) -> dict[str, object]:
    """The line that closes stdout. It carries ``stopped``; no input line does."""
    lines = stdout.splitlines()
    assert lines, stdout
    summary = json.loads(lines[-1])
    assert "stopped" in summary, stdout
    return summary


def one_line(stdout: str) -> dict[str, object]:
    lines = input_lines(stdout)
    assert len(lines) == 1, stdout
    return lines[0]


def first_line(stdout: str) -> dict[str, object]:
    """The seed's line. A run prints one line per input, so the solver's may follow it."""
    lines = input_lines(stdout)
    assert lines, stdout
    return lines[0]


def two_lines(stdout: str) -> tuple[dict[str, object], dict[str, object]]:
    lines = input_lines(stdout)
    assert len(lines) == 2, stdout
    return lines[0], lines[1]
