"""Acceptance tests for the pass-keywords-through-a-downgrade bug.

Each test spawns ``python -P -m pyct`` through the harness: the bug was a keyword the
target wrote reaching pyct's wrapper instead of str's own method, and only a real run
shows what the target was handed and whose raise the line reports.
"""

import pytest

from tests.acceptance.harness import REPO_ROOT, one_line, run_pyct

SPLIT_KEYWORD = "targets.strs.split_keyword::split_on_comma"
SPLIT_KEYWORD_FILE = str(REPO_ROOT / "targets" / "strs" / "split_keyword.py")
ENCODE_KEYWORD = "targets.strs.encode_keyword::encode_utf8"
ENCODE_FORMS = "targets.strs.encode_forms::encode_three_ways"
FORMAT_KEYWORD = "targets.strs.format_keyword::fill"
FORMAT_KEYWORD_FILE = str(REPO_ROOT / "targets" / "strs" / "format_keyword.py")
ENCODE_UNKNOWN_KEYWORD = "targets.strs.encode_unknown_keyword::encode_bogus"
# the `return` under each target's `if`, run only when the call handed back Python's answer
UNDER_THE_FORK = 4


def covered_in(line: dict[str, object], file: str) -> list[int]:
    """The lines one input covered in one file, narrowed so a membership test means something."""
    covered = line["covered"]
    assert isinstance(covered, dict), line
    lines = covered[file]
    assert isinstance(lines, list), line
    return lines


# pass-keywords-through-a-downgrade-returns-what-python-returns
def test_returns_what_python_returns() -> None:
    result = run_pyct(SPLIT_KEYWORD, '{"s": "a,b"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    # str's own split handed back ["a", "b"], so the target went under its `if`
    assert UNDER_THE_FORK in covered_in(seed, SPLIT_KEYWORD_FILE)


# pass-keywords-through-a-downgrade-names-the-method
def test_names_the_method() -> None:
    result = run_pyct(ENCODE_KEYWORD, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    # named by the method, as the positional call is; the bytes it hands back are plain
    assert seed["downgrades"] == [{"name": "encode", "count": 1}]
    assert seed["forks"] == []


# pass-keywords-through-a-downgrade-counts-every-form-as-one-method
def test_counts_every_form_as_one_method() -> None:
    result = run_pyct(ENCODE_FORMS, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    # positional, keyword and mixed are one method called three times in a row
    assert seed["downgrades"] == [{"name": "encode", "count": 3}]


# pass-keywords-through-a-downgrade-passes-any-keyword-name
def test_passes_any_keyword_name() -> None:
    result = run_pyct(FORMAT_KEYWORD, '{"s": "{x}"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["downgrades"] == [{"name": "format", "count": 1}]
    # `x` is a name the target's own format field chose, and str's format filled it with 1
    assert UNDER_THE_FORK in covered_in(seed, FORMAT_KEYWORD_FILE)


# pass-keywords-through-a-downgrade-raises-what-python-raises
def test_raises_what_python_raises() -> None:
    result = run_pyct(ENCODE_UNKNOWN_KEYWORD, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # the detail is str's own sentence, and 3.13 reworded it, so plain Python on the
    # interpreter the harness ran pyct with gives the expected text; the raise is the target's
    with pytest.raises(TypeError) as plain:
        "abc".encode(bogus=1)  # pyrefly: ignore[unexpected-keyword]
    assert seed["failure"] == {
        "kind": "target_raised",
        "detail": f"TypeError: {plain.value}",
    }
    assert seed["downgrades"] == []
