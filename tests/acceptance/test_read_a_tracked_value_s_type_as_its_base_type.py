"""Acceptance tests for the read-a-tracked-value-s-type-as-its-base-type bug.

A tracked value reports its base type as its class in any code, a call written `type(v)` in the
target's package answers that base type, and a tracked class called with a value builds its
base type's plain value. Each test runs pyct through the command line: the bug was a type check
taking the side Python does not take, which only a real run shows. The targets in
``targets/scope/shop`` run from ``targets/scope``, so ``measure`` beside them is a package of its
own, outside the target's, as a library is.
"""

from pathlib import Path

import pytest

from targets.types import copied, dispatched, matched, own_type, read
from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    run_pyct,
    second_line,
    summary_line,
)
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in

TYPES = REPO_ROOT / "targets" / "types"
READ_FILE = TYPES / "read.py"
SCOPE = REPO_ROOT / "targets" / "scope"
TYPED_FILE = SCOPE / "shop" / "typed.py"
EVERY_TYPE = '{"n": 1, "r": 2.5, "s": "a", "b": true, "xs": [1]}'
EACH_KIND = '{"flag": true, "x": 1, "r": 2.5, "s": "a", "xs": [1]}'


def line_of(file: Path, text: str, function: str | None = None) -> int:
    """The number of the first line in a fixture that holds this text, after the line that
    defines ``function`` when one is named, so each target finds its own line."""
    lines = file.read_text().splitlines()
    start = (
        0
        if function is None
        else lines.index(next(line for line in lines if line.startswith(f"def {function}(")))
    )
    return next(number for number, line in enumerate(lines, 1) if number > start and text in line)


def covers_plainly(
    target: str, seed: str, file: Path, returned: str, *argv: str, cwd: Path = REPO_ROOT
) -> dict[str, object]:
    """Run the target, and check the seed's line: it covers the line that returns ``returned``,
    with no failure, no fork and no downgrade. The line comes back for more checks."""
    result = run_pyct(target, seed, *argv, cwd=cwd)

    assert result.returncode == 0, result.stderr
    line = first_line(result.stdout)
    assert line["failure"] is None, line
    function = target.rpartition("::")[2]
    assert line_of(file, f'return "{returned}"', function) in covered_in(line, str(file))
    assert line["forks"] == []
    assert line["downgrades"] == []
    return line


def raised(line: dict[str, object], error: BaseException) -> None:
    """Check that a line says the target raised this error, in Python's own words."""
    detail = f"{type(error).__name__}: {error}"
    assert line["failure"] == {"kind": "target_raised", "detail": detail}, line


def python_raise(call: object) -> BaseException:
    """What a call raises on plain values in this run."""
    assert callable(call)
    try:
        call()
    except Exception as error:
        return error
    raise AssertionError("the call did not raise")


# read-a-tracked-value-s-type-as-its-base-type-reads-each-type-as-python-s
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_reads_each_type_as_python_s(where: tuple[str, ...]) -> None:
    assert read.each_type(1, 2.5, "a", True, [1]) == "base"
    covers_plainly("targets.types.read::each_type", EVERY_TYPE, READ_FILE, "base", *where)
    # a tracked range, which a call written `range(n)` builds, reads as Python's range too
    assert read.range_type(2) == "base"
    covers_plainly("targets.types.read::range_type", '{"n": 2}', READ_FILE, "base", *where)


# read-a-tracked-value-s-type-as-its-base-type-follows-past-a-type-guard
def test_follows_past_a_type_guard() -> None:
    result = run_pyct("targets.types.read::guarded", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    guard = line_of(READ_FILE, "if type(x) is int and x > 3:")
    seed = first_line(result.stdout)
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (guard, [">", "x", 3], False)
    ]
    assert seed["downgrades"] == []
    solved = second_line(result.stdout)
    assert argument(solved, "x") > 3
    assert line_of(READ_FILE, 'return "big"') in covered_in(solved, str(READ_FILE))
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# read-a-tracked-value-s-type-as-its-base-type-answers-isinstance-of-a-bool
def test_answers_isinstance_of_a_bool() -> None:
    assert read.bool_checks(True, 1) == "bool"
    covers_plainly("targets.types.read::bool_checks", '{"flag": true, "x": 1}', READ_FILE, "bool")


# read-a-tracked-value-s-type-as-its-base-type-reads-the-class-and-its-name
def test_reads_the_class_and_its_name() -> None:
    seed = '{"n": 1, "s": "a", "flag": true, "xs": [1]}'
    assert read.class_and_name(1, "a", True, [1]) == "base"
    covers_plainly("targets.types.read::class_and_name", seed, READ_FILE, "base")


# read-a-tracked-value-s-type-as-its-base-type-answers-isinstance-in-a-library
def test_answers_isinstance_in_a_library() -> None:
    seed = '{"flag": true, "x": 1}'
    covers_plainly("shop.typed::checks", seed, TYPED_FILE, "python", cwd=SCOPE)
    covers_plainly("shop.typed::ranged", '{"n": 2}', TYPED_FILE, "python", cwd=SCOPE)


# read-a-tracked-value-s-type-as-its-base-type-picks-the-bool-handler-in-singledispatch
def test_picks_the_bool_handler_in_singledispatch() -> None:
    assert dispatched.f(True, 1, 2.5, "a", [1]) == "python"
    file = TYPES / "dispatched.py"
    covers_plainly("targets.types.dispatched::f", EACH_KIND, file, "python")


# read-a-tracked-value-s-type-as-its-base-type-matches-a-class-pattern
def test_matches_a_class_pattern() -> None:
    assert matched.f(True, 1, 2.5, "a", [1]) == "python"
    file = TYPES / "matched.py"
    seed = covers_plainly("targets.types.matched::f", EACH_KIND, file, "python")
    # the body under `case bool():`
    assert line_of(file, 'return "bool"') in covered_in(seed, str(file))


# read-a-tracked-value-s-type-as-its-base-type-copies-and-pickles-as-before
def test_copies_and_pickles_as_before() -> None:
    result = run_pyct("targets.types.copied::f", '{"n": 3, "xs": [1]}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
    assert [fork["expression"] for fork in forks_of(seed)] == [
        [">", "n", 10],
        [">", "n", 0],
        [">", ["len", "xs"], 2],
    ]
    # each pickle of a tracked value is a downgrade where `pickle.dumps` runs
    at = "targets/types/copied.py"
    assert seed["downgrades"] == [
        downgrade("__reduce_ex__", 1, f"{at}:9:21"),
        downgrade("__reduce_ex__", 1, f"{at}:10:21"),
    ]
    # plain Python appends "b" alone for these arguments
    assert copied.f(3, [1]) == ["b"]
    file = TYPES / "copied.py"
    covered = covered_in(seed, str(file))
    assert line_of(file, 'seen.append("b")') in covered
    for name in "acde":
        assert line_of(file, f'seen.append("{name}")') not in covered


# read-a-tracked-value-s-type-as-its-base-type-builds-a-plain-value-through-the-type
def test_builds_a_plain_value_through_the_type() -> None:
    assert read.rebuilt(1, 2.5, "a", True, [1]) == "plain"
    covers_plainly("targets.types.read::rebuilt", EVERY_TYPE, READ_FILE, "plain")


# read-a-tracked-value-s-type-as-its-base-type-builds-a-plain-value-outside-the-package
def test_builds_a_plain_value_outside_the_package() -> None:
    covers_plainly("shop.typed::rebuilt", EVERY_TYPE, TYPED_FILE, "plain", cwd=SCOPE)


# read-a-tracked-value-s-type-as-its-base-type-keeps-a-module-s-own-type
def test_keeps_a_module_s_own_type() -> None:
    assert own_type.f(0) == "own" and read.built(0) == "built"
    file = TYPES / "own_type.py"
    covers_plainly("targets.types.own_type::f", '{"x": 0}', file, "own")
    covers_plainly("targets.types.read::built", '{"x": 0}', READ_FILE, "built")


# read-a-tracked-value-s-type-as-its-base-type-leaves-other-answers-alone
def test_leaves_other_answers_alone() -> None:
    assert read.other_answers(1, True) == "python"
    covers_plainly(
        "targets.types.read::other_answers", '{"n": 1, "flag": true}', READ_FILE, "python"
    )


# read-a-tracked-value-s-type-as-its-base-type-raises-python-s-error-through-the-type
@pytest.mark.parametrize(
    ("target", "cwd"),
    [
        ("targets.types.read::rebuilt_from_text", REPO_ROOT),
        ("shop.typed::rebuilt_from_text", SCOPE),
    ],
    ids=["in-the-package", "outside-it"],
)
def test_raises_python_s_error_through_the_type(target: str, cwd: Path) -> None:
    result = run_pyct(target, '{"x": 0}', cwd=cwd)

    assert result.returncode == 0, result.stderr
    raised(first_line(result.stdout), python_raise(lambda: int("abc")))


# read-a-tracked-value-s-type-as-its-base-type-raises-python-s-error-for-a-bad-check
@pytest.mark.parametrize(
    ("target", "seed", "call"),
    [
        ("two_argument_type", '{"x": 0}', lambda: read.two_argument_type(0)),
        ("checked_against_a_number", '{"flag": true}', lambda: read.checked_against_a_number(True)),
    ],
    ids=["type", "isinstance"],
)
def test_raises_python_s_error_for_a_bad_check(target: str, seed: str, call: object) -> None:
    result = run_pyct(f"targets.types.read::{target}", seed)

    assert result.returncode == 0, result.stderr
    error = python_raise(call)
    assert isinstance(error, TypeError)
    raised(first_line(result.stdout), error)
