from pathlib import Path

import pytest

from tests.line_limits import MAX_BODY_LINES, MAX_FILE_LINES, check_file, main


def function_of(body_lines: int, docstring: str = "") -> str:
    """A function whose body after the docstring is ``body_lines`` lines long."""
    body = "".join(f"    x{n} = {n}\n" for n in range(body_lines))
    return f"def long_one():\n{docstring}{body}"


def write(tmp_path: Path, text: str, name: str = "module.py") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_a_body_at_the_cap_passes(tmp_path: Path) -> None:
    path = write(tmp_path, function_of(MAX_BODY_LINES))

    assert check_file(path) == []


def test_a_body_one_line_over_the_cap_is_named_with_its_line(tmp_path: Path) -> None:
    path = write(tmp_path, "import os\n\n\n" + function_of(MAX_BODY_LINES + 1))

    (broken,) = check_file(path)

    assert str(broken) == (
        f"{path}:4: function-body-lines long_one has {MAX_BODY_LINES + 1} body lines, "
        f"at most {MAX_BODY_LINES}"
    )


def test_the_docstring_is_not_part_of_the_body(tmp_path: Path) -> None:
    docstring = '    """One line.\n\n    And a paragraph after it.\n    """\n'
    path = write(tmp_path, function_of(MAX_BODY_LINES, docstring))

    assert check_file(path) == []


def test_blank_lines_and_comments_inside_the_body_count(tmp_path: Path) -> None:
    body = "    x = 1\n" + "\n    # a comment\n" * (MAX_BODY_LINES // 2) + "    return x\n"
    path = write(tmp_path, f"def long_one():\n{body}")

    (broken,) = check_file(path)

    assert broken.rule == "function-body-lines"


def test_methods_async_functions_and_nested_functions_are_checked(tmp_path: Path) -> None:
    inner = "".join(f"            y{n} = {n}\n" for n in range(MAX_BODY_LINES + 1))
    text = (
        "class Holder:\n"
        "    async def method(self):\n"
        "        def nested():\n"
        f"{inner}"
        "        return nested\n"
    )
    path = write(tmp_path, text)

    # the method holds the nested function, so both run past the cap
    assert [broken.line for broken in check_file(path)] == [2, 3]


def test_a_file_at_the_cap_passes(tmp_path: Path) -> None:
    path = write(tmp_path, "x = 1\n" * MAX_FILE_LINES)

    assert check_file(path) == []


def test_a_file_one_line_over_the_cap_is_named(tmp_path: Path) -> None:
    path = write(tmp_path, "x = 1\n" * (MAX_FILE_LINES + 1))

    (broken,) = check_file(path)

    assert str(broken) == (
        f"{path}:1: file-lines {MAX_FILE_LINES + 1} lines, at most {MAX_FILE_LINES}"
    )


def test_a_file_that_does_not_parse_is_reported_rather_than_raised(tmp_path: Path) -> None:
    path = write(tmp_path, "x = 1\ndef broken(:\n")

    (broken,) = check_file(path)

    assert (broken.line, broken.rule) == (2, "syntax")


def test_main_prints_each_break_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    long_file = write(tmp_path, "x = 1\n" * (MAX_FILE_LINES + 1), "long.py")
    (tmp_path / "sub").mkdir()
    write(tmp_path, "", "sub/fine.py")
    long_function = write(tmp_path, function_of(MAX_BODY_LINES + 1), "sub/long.py")

    code = main([str(tmp_path)])

    lines = capsys.readouterr().out.splitlines()
    assert code == 1
    assert lines[0].startswith(f"{long_file}:1: file-lines ")
    assert lines[1].startswith(f"{long_function}:1: function-body-lines ")
    assert lines[2] == "Line limits: 3 files checked, 2 broken."


def test_main_exits_0_when_every_file_keeps_the_limits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, function_of(MAX_BODY_LINES))

    code = main([str(path)])

    assert code == 0
    assert capsys.readouterr().out == "Line limits: 1 file checked, 0 broken.\n"


def test_main_refuses_a_path_that_is_not_there(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    code = main([str(missing)])

    assert code == 2
    assert capsys.readouterr().err == f"line_limits: no such file or directory: {missing}\n"


def test_main_refuses_to_run_without_a_path(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])

    assert code == 2
    assert capsys.readouterr().err == "usage: python -m tests.line_limits PATH [PATH ...]\n"
