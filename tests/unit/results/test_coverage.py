from pathlib import Path

from pyct.results.coverage import Coverage, Scope, executable_lines, no_gain

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


def test_coverage_counts_the_lines_it_was_measured_against() -> None:
    coverage = Coverage(covered={"m.py": frozenset({2})}, lines={"m.py": frozenset({1, 2, 3})})

    assert coverage.total == {"m.py": 3}


def test_coverage_names_the_lines_no_input_ran() -> None:
    coverage = Coverage(covered={"m.py": frozenset({2})}, lines={"m.py": frozenset({1, 2, 3})})

    assert coverage.uncovered == {"m.py": frozenset({1, 3})}


def test_coverage_leaves_a_fully_covered_file_nothing_uncovered() -> None:
    # the file is still a key, so a reader of one map finds the same files in the other
    coverage = Coverage(covered={"m.py": frozenset({1, 2})}, lines={"m.py": frozenset({1, 2})})

    assert coverage.uncovered == {"m.py": frozenset()}


def test_coverage_of_a_scope_keeps_the_lines_it_measured_against() -> None:
    scope = Scope(file="m.py", lines=frozenset({1, 2, 3}))

    coverage = Coverage.of(scope, raw_lines=frozenset({2, 99}))

    assert coverage.lines == {"m.py": frozenset({1, 2, 3})}
    assert coverage.uncovered == {"m.py": frozenset({1, 3})}


def test_no_gain_is_true_when_the_last_input_covered_nothing_new() -> None:
    covered = [frozenset({1, 2}), frozenset({1})]

    assert no_gain(covered, 1) is True


def test_no_gain_is_false_when_an_input_inside_the_window_gained() -> None:
    covered = [frozenset({1, 2}), frozenset({1})]

    # the seed gained every line it ran, so a window of two reaches a gain
    assert no_gain(covered, 2) is False


def test_no_gain_counts_a_line_an_earlier_input_added_as_no_gain() -> None:
    covered = [frozenset({1}), frozenset({1, 2}), frozenset({2})]

    # the third only repeats the line the second added first
    assert no_gain(covered, 1) is True


def test_no_gain_is_false_when_the_last_input_added_a_line() -> None:
    covered = [frozenset({1}), frozenset({1, 2}), frozenset({3})]

    assert no_gain(covered, 1) is False


def test_no_gain_is_false_with_fewer_inputs_than_the_plateau() -> None:
    assert no_gain([frozenset({1})], 2) is False


def test_no_gain_is_false_before_any_input_ran() -> None:
    assert no_gain([], 1) is False
