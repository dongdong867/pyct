"""A target's own lines, read from the file by Python's parser."""

import ast
from pathlib import Path

import pytest

from tools.compare_coverage import body as body_module
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


def test_own_lines_are_the_lines_the_body_runs_at_each_statements_first_line(
    tmp_path: Path,
) -> None:
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


def test_a_class_is_the_bodies_of_its_methods(tmp_path: Path) -> None:
    body = read_body(write(tmp_path), "Box")

    # the class line, its docstring, size = 1 and the method's def line run at import
    assert body.own_lines == frozenset({54})
    assert body.cut([48, 49, 51, 53, 54]) == frozenset({54})


# the three shapes whose lines compile to no code a call runs
SHAPES = '''\
COUNT = 0


def tally(x):
    """Count x in, through an inner function."""
    global COUNT
    step = 1

    def bump():
        nonlocal step
        step += x

    bump()
    COUNT += step
    return step


def logged(fn):
    return fn


class Counter:
    """A counter."""

    start = 0

    @staticmethod
    @logged
    def of(n):
        return n

    class Inner:
        depth = 1

        def deeper(self):
            return self.depth


@logged
@logged
def wrapped(x):
    return x
'''


def test_a_function_leaves_out_its_def_docstring_global_and_nonlocal_lines(
    tmp_path: Path,
) -> None:
    body = read_body(write(tmp_path, SHAPES), "tally")

    # the inner function's def line and body run during the call
    assert body.own_lines == frozenset({7, 9, 11, 13, 14, 15})
    assert body.cut([4, 5, 6, 10]) == frozenset()


def test_a_class_leaves_out_its_class_level_lines_and_each_method_def_line(
    tmp_path: Path,
) -> None:
    body = read_body(write(tmp_path, SHAPES), "Counter")

    # a nested class is class-level code too; its methods' bodies are the class's own lines
    assert body.own_lines == frozenset({30, 36})
    assert body.cut(range(22, 37)) == frozenset({30, 36})


def test_a_decorated_function_leaves_out_its_decorators(tmp_path: Path) -> None:
    body = read_body(write(tmp_path, SHAPES), "wrapped")

    assert body.own_lines == frozenset({42})
    assert body.cut([39, 40, 41, 42]) == frozenset({42})


GENERIC = """\
def generic[T](x: T) -> T:
    y = x
    return y


class Box[T]:
    size = 1

    def get[U](self, u: U) -> U:
        return u
"""


def test_a_generic_function_and_class_are_read_through_their_type_parameters(
    tmp_path: Path,
) -> None:
    file = write(tmp_path, GENERIC)

    assert read_body(file, "generic").own_lines == frozenset({2, 3})
    assert read_body(file, "Box").own_lines == frozenset({10})


def test_a_definition_with_no_compiled_code_is_refused_naming_the_file(tmp_path: Path) -> None:
    file = write(tmp_path, "def f():\n    return 1\n")
    (definition,) = ast.parse(file.read_text()).body
    assert isinstance(definition, ast.FunctionDef)

    with pytest.raises(BodyError, match=rf"{file} compiles no code for f at line 1"):
        body_module._find({}, definition, file)


def test_a_module_that_does_not_compile_is_refused_naming_it(tmp_path: Path) -> None:
    file = write(tmp_path, "def f():\n    nonlocal y\n")

    with pytest.raises(BodyError, match=rf"{file} does not compile: .*nonlocal"):
        read_body(file, "f")


def test_the_last_definition_of_the_name_is_the_target(tmp_path: Path) -> None:
    file = write(tmp_path, "def f():\n    return 1\n\n\nasync def f():\n    return 2\n")

    assert read_body(file, "f").own_lines == frozenset({6})


def test_a_name_bound_without_def_or_class_is_refused_naming_the_file(tmp_path: Path) -> None:
    file = write(tmp_path, "def g():\n    return 1\n\n\nf = g\n")

    with pytest.raises(BodyError, match=rf"{file} has no top-level def or class named f"):
        read_body(file, "f")


@pytest.mark.parametrize(
    "rebinding",
    ["f = g", "f: object = g", "(f, h) = (g, g)", "import os as f", "from os import path as f"],
)
def test_a_name_bound_again_after_its_definition_is_refused(tmp_path: Path, rebinding: str) -> None:
    file = write(tmp_path, f"def g():\n    return 1\n\n\ndef f():\n    return 2\n\n\n{rebinding}\n")

    with pytest.raises(BodyError, match=rf"{file} binds f again at line 9, after its def"):
        read_body(file, "f")


def test_a_name_bound_before_its_definition_is_its_definition(tmp_path: Path) -> None:
    file = write(tmp_path, "from os import path as f\nf = 1\n\n\ndef f():\n    return 2\n")

    assert read_body(file, "f").own_lines == frozenset({6})


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
