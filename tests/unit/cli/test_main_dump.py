"""main writes each ask's programs to the dump folder, and a write that fails mid-run stops the
dump, not the run."""

from pathlib import Path
from typing import Any

import pytest

from pyct import cli
from pyct.cli import main
from pyct.results.record import RunResult
from tests.acceptance.harness import input_lines, let_pyct_run_in_process, summary_line

# line 2 `if x > 0:` flips sat; line 3 `if x < 0:` under it is unsat: two asks
NESTED = "targets.asks.sat_then_unsat::nested"


def test_a_dump_write_that_fails_stops_the_dump_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    let_pyct_run_in_process(monkeypatch)
    calls: list[int] = []

    def refused(folder: Path, number: int, *_: object) -> None:
        calls.append(number)
        raise PermissionError(13, "Permission denied", str(folder / f"ask-{number}.smt2"))

    monkeypatch.setattr("pyct.cli.write", refused)

    code = main(["run", NESTED, '{"x": 0}', "--dump-formulas", str(tmp_path / "D")])

    assert code == 0
    captured = capsys.readouterr()
    assert len(input_lines(captured.out)) == 2
    assert summary_line(captured.out)["stopped"] == "no fork to flip"
    # one warning naming the file and why, and no write tried after it
    warnings = [line for line in captured.err.splitlines() if line.startswith("cannot write")]
    assert warnings == [
        f"cannot write {tmp_path / 'D' / 'ask-1.smt2'}: Permission denied; writing no more asks"
    ]
    assert calls == [1]


def test_a_relative_dump_folder_stays_where_it_was_when_the_target_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    let_pyct_run_in_process(monkeypatch)
    folder = tmp_path / "D"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(tmp_path)

    def moved(*args: Any, **kwargs: Any) -> RunResult:
        monkeypatch.chdir(elsewhere)
        return real(*args, **kwargs)

    real = cli.run
    monkeypatch.setattr(cli, "run", moved)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))

    assert main(["run", NESTED, '{"x": 0}', "--dump-formulas", "D"]) == 0

    assert sorted(path.name for path in folder.iterdir()) == ["ask-1.smt2", "ask-2.smt2"]
    assert not (elsewhere / "D").exists()
