"""A target's own lines, read from the file by Python's parser."""

from pathlib import Path

import pytest

from tools.compare_coverage.body import BodyError, read_body

SOURCE = '''"""A module."""

import os


def helper(x):
    return x


@some.decorator(
    "arg",
)
def target(x,
           y):
    """Its docstring,
    over two lines."""
    total = (x
             + y)
    if total > 1:
        return helper(total)
    else:
        pass
    try:
        os.stat("x")
    except OSError:
        total = 0
    finally:
        total += 1

    def inner():
        """Inner's docstring."""
        return 1

    @dec
    def decorated():
        return 2

    match total:
        case 1:
            return 1
    for i in range(2):
        continue
    else:
        total = 3
    return total


class Box:
    """A box."""

    size = 1

    def grow(self):
        self.size += 1
'''


def write(tmp_path: Path, text: str = SOURCE) -> Path:
    file = tmp_path / "module.py"
    file.write_text(text)
    return file


def test_own_lines_are_every_statement_in_the_body_at_its_first_line(tmp_path: Path) -> None:
    body = read_body(write(tmp_path), "target")

    expected = {17, 19, 20, 22, 23, 24, 26, 28, 30, 32, 35, 36, 38, 40, 41, 42, 44, 45}
    assert body.own_lines == frozenset(expected)


def test_a_line_inside_a_statement_stands_for_the_statement(tmp_path: Path) -> None:
    body = read_body(write(tmp_path), "target")

    assert body.cut([17, 18]) == frozenset({17})
    # the else line is inside the if statement; a nested decorator stands for its def
    assert body.cut([21]) == frozenset({19})
    assert body.cut([34]) == frozenset({35})
    # a line inside an inner statement stands for that statement, not the outer one
    assert body.cut([20, 24, 26]) == frozenset({20, 24, 26})


def test_the_def_line_its_decorators_signature_and_docstring_are_not_own_lines(
    tmp_path: Path,
) -> None:
    body = read_body(write(tmp_path), "target")

    assert body.cut([10, 11, 12, 13, 14, 15, 16]) == frozenset()


def test_lines_outside_the_body_are_dropped(tmp_path: Path) -> None:
    body = read_body(write(tmp_path), "target")

    assert body.cut([1, 3, 6, 7, 999]) == frozenset()


def test_a_class_body_holds_its_methods(tmp_path: Path) -> None:
    body = read_body(write(tmp_path), "Box")

    assert body.own_lines == frozenset({51, 53, 54})


def test_the_last_definition_of_the_name_is_the_target(tmp_path: Path) -> None:
    file = write(tmp_path, "def f():\n    return 1\n\n\nasync def f():\n    return 2\n")

    assert read_body(file, "f").own_lines == frozenset({6})


def test_a_name_bound_without_def_or_class_is_refused_naming_the_file(tmp_path: Path) -> None:
    file = write(tmp_path, "def g():\n    return 1\n\n\nf = g\n")

    with pytest.raises(BodyError, match=rf"{file} has no top-level def or class named f"):
        read_body(file, "f")


def test_a_nested_definition_is_not_top_level(tmp_path: Path) -> None:
    file = write(tmp_path, "def g():\n    def f():\n        return 1\n    return f\n")

    with pytest.raises(BodyError, match="no top-level def or class named f"):
        read_body(file, "f")


def test_a_missing_file_is_refused_naming_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    with pytest.raises(BodyError, match=rf"cannot read {missing}"):
        read_body(missing, "f")


def test_a_file_that_does_not_parse_is_refused_naming_it(tmp_path: Path) -> None:
    file = write(tmp_path, "def f(:\n")

    with pytest.raises(BodyError, match=rf"{file} does not parse"):
        read_body(file, "f")
