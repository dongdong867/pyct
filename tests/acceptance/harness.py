"""What every acceptance test needs: spawn pyct, run it in process, read its stdout.

The line helpers narrow a field of one printed line. ``argument``, ``forks_of`` and
``numbers_of`` assert the type of the field they read, with the line in the message.

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

# a child that inherits either one starts coverage.py and is measured
COVERAGE_STARTUP = ("COVERAGE_PROCESS_CONFIG", "COVERAGE_PROCESS_START")


def run_pyct(
    *argv: str,
    path: str | None = None,
    cwd: Path = REPO_ROOT,
    unset: tuple[str, ...] = (),
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    """Spawn ``pyct run`` with the given argv from ``cwd``. ``path`` replaces the child's ``PATH``.

    ``unset`` names more variables the child does not inherit.

    ``timeout`` is the seconds the child gets before the test fails, for a run whose own budget
    is longer than the usual 30.

    A run given ``--budget SECONDS`` or ``--budget=SECONDS`` arms pyct's deadline, and the
    deadline firing inside coverage.py's tracer hangs the child, as
    ``tests/unit/deadline_fires.py`` says. So that run leaves coverage.py out.
    """
    budget = any(arg == "--budget" or arg.startswith("--budget=") for arg in argv)
    left_out = {"PYTHONPATH", *unset, *(COVERAGE_STARTUP if budget else ())}
    env = {k: v for k, v in os.environ.items() if k not in left_out}
    if path is not None:
        env["PATH"] = path
    result = subprocess.run(
        [sys.executable, "-P", "-m", "pyct", "run", *argv],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # the timeout test spawns a target that never returns, so a broken
        # budget has to fail the test instead of hanging the suite
        timeout=timeout,
    )
    check_every_uncovered_line_explained_once(result.stdout)
    # a line no cause explains is put down as ended before with no input that ended
    assert "no cause explains line" not in result.stderr, result.stderr
    return result


def check_every_uncovered_line_explained_once(stdout: str) -> None:
    """Fail unless the summary's ``why_uncovered`` names each uncovered line exactly once.

    Every run the acceptance suite makes passes through here, so each target it
    runs proves see-why-a-line-was-missed-accounts-for-every-uncovered-line-once.
    A run with no summary line, such as a refused seed, has nothing to check.
    """
    lines = stdout.splitlines()
    summary = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
    if "stopped" not in summary:
        return
    named: dict[str, list[int]] = {}
    for entry in summary["why_uncovered"]:
        named.setdefault(entry["file"], []).extend(entry["lines"])
    for file, uncovered in summary["uncovered"].items():
        assert sorted(named.pop(file, [])) == uncovered, (file, summary["why_uncovered"])
    assert not named, named


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


def hanging_cvc5(tmp_path: Path) -> Path:
    """A cvc5 that says its version at once but never answers a formula, for ``run_pyct``.

    It reads the formula and then sleeps an hour, far past the limits these
    tests give it, so only pyct can end the solve. ``exec`` makes the sleep
    the script's own process, so ending that process ends the sleep too.
    """
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        'if [ "$1" = "--version" ]; then\n'
        "    echo 'cvc5 1.3.4'\n"
        "    exit 0\n"
        "fi\n"
        "cat > /dev/null\n"
        "exec sleep 3600\n"
    )
    script.chmod(0o755)
    return script


def downgrade(name: str, count: int, at: str) -> dict[str, object]:
    """A downgrade entry as an input's line writes it. ``at`` is ``targets/<file>.py:line:col``."""
    path, line, col = at.rsplit(":", 2)
    return {
        "name": name,
        "count": count,
        "file": str(REPO_ROOT / path),
        "line": int(line),
        "col": int(col),
    }


def input_lines(stdout: str) -> list[dict[str, object]]:
    """The one line per input, without the summary line that closes stdout.

    A tool tells the summary from an input line by its ``stopped`` key, and
    that is how this tells them apart too; the summary has to be there, so a
    run that lost it fails every test that counts lines.
    """
    lines = [json.loads(line) for line in stdout.splitlines()]
    assert lines and "stopped" in lines[-1], stdout
    return lines[:-1]


def answered(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    """The input lines without a last one the run's deadline cut short.

    That input left its plan where the budget stopped it, not where an
    answer took it, so a check that every answer stays on its plan leaves
    it out. Only the last input can be cut so.
    """
    if lines and lines[-1]["failure"] == {"kind": "timeout", "detail": "deadline passed"}:
        return lines[:-1]
    return lines


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


def second_line(stdout: str) -> dict[str, object]:
    """The first solver input's line. The loop may have run more inputs after it."""
    lines = input_lines(stdout)
    assert len(lines) > 1, stdout
    return lines[1]


def two_lines(stdout: str) -> tuple[dict[str, object], dict[str, object]]:
    lines = input_lines(stdout)
    assert len(lines) == 2, stdout
    return lines[0], lines[1]


def argument(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


def forks_of(line: dict[str, object]) -> list[dict[str, object]]:
    """The forks off a printed line, narrowed so a field lookup means something."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [dict(fork) for fork in forks]


def lines_expressions_and_sides(line: dict[str, object]) -> list[tuple[object, object, object]]:
    """Each fork on a printed line, by its line, its expression and the side it took."""
    return [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(line)]


def took(inputs: list[dict[str, object]], fork: tuple[object, object, object]) -> bool:
    """Whether any of the printed lines took this fork: its line, its expression and its side."""
    return any(fork in lines_expressions_and_sides(line) for line in inputs)


def numbers_of(line: dict[str, object], key: str) -> dict[str, list[int]]:
    """One map of line numbers off a printed line, narrowed so a lookup means something."""
    payload = line[key]
    assert isinstance(payload, dict), line
    return {str(file): [int(number) for number in lines] for file, lines in payload.items()}


def union_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        for file, covered in numbers_of(line, "covered").items():
            union[file] = union.get(file, set()) | set(covered)
    return {file: sorted(covered) for file, covered in union.items()}


def version_then_crashing_cvc5(tmp_path: Path) -> Path:
    """A cvc5 that says its version at once and dies on every formula, for a ``PATH``.

    pyct finds it, reports its version, and stops with ``solver failed`` at the first solve.
    """
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        'if [ "$1" = "--version" ]; then\n'
        "    echo 'cvc5 1.3.4'\n"
        "    exit 0\n"
        "fi\n"
        "cat > /dev/null\n"
        f"echo '{CRASH_DETAIL}' >&2\n"
        "exit 1\n"
    )
    script.chmod(0o755)
    return script
