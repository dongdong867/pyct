from pathlib import Path

from pyct.results.coverage import Coverage, Scope, executable_lines

FIXTURE = Path(__file__).resolve().parents[3] / "targets" / "trace" / "uncalled_helper.py"


def test_executable_lines_counts_every_line_in_the_module() -> None:
    # docstring, two def lines, the four body lines; no blank or comment lines, no line 0
    assert executable_lines(str(FIXTURE)) == frozenset({1, 4, 5, 6, 7, 10, 11})


def test_scope_of_module_names_the_file_and_its_lines() -> None:
    scope = Scope.of_module(str(FIXTURE))

    assert scope.file == str(FIXTURE)
    assert scope.lines == executable_lines(str(FIXTURE))


def test_coverage_keeps_only_lines_in_scope() -> None:
    scope = Scope(file="m.py", lines=frozenset({1, 2, 3}))

    coverage = Coverage.of(scope, raw_lines=frozenset({2, 3, 99}))

    assert coverage.covered == {"m.py": frozenset({2, 3})}
    assert coverage.total == {"m.py": 3}
