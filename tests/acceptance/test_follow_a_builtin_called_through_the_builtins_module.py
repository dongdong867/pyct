"""Acceptance tests for follow-a-builtin-called-through-the-builtins-module.

A call of `len`, `ord` or `chr` through a name a module of the target's package binds only to
the `builtins` module, or only to that function imported from it, gives the answer the bare call
gives there. Each test runs pyct through the command line, since only a run through it
substitutes the module's calls.
"""

import json

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    forks_of,
    input_lines,
    numbers_of,
    run_pyct,
    union_of,
)

INTERCEPT = REPO_ROOT / "targets" / "intercept"
BUILTINS_LEN = "targets.intercept.builtins_len::check"
LEN_FILE = str(INTERCEPT / "builtins_len.py")
SPELLINGS = "targets.intercept.builtins_spellings"
BARE = "targets.intercept.builtins_bare"
STAR = "targets.intercept.builtins_star"
RAISES = "targets.intercept.builtins_raises"
SCOPE = REPO_ROOT / "targets" / "scope"
ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"
LONGER = [">", ["len", "s"], 3]


def taken(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each fork on a printed line, by its expression and the side it took."""
    return [(fork["expression"], fork["taken"]) for fork in forks_of(line)]


def named_downgrades(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each downgrade on a printed line, by its name and count."""
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [(each["name"], each["count"]) for each in downgrades]


def python_raise(call: object) -> BaseException:
    """What a call raises on plain values in this run."""
    assert callable(call)
    try:
        call()
    except Exception as error:
        return error
    raise AssertionError("the call did not raise")


# follow-a-builtin-called-through-the-builtins-module-follows-len-through-the-builtins-module
def test_follows_len_through_the_builtins_module() -> None:
    result = run_pyct(BUILTINS_LEN, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert taken(inputs[0]) == [(LONGER, False)]
    assert inputs[0]["downgrades"] == []
    longer = [line for line in inputs[1:] if (LONGER, True) in taken(line)]
    assert longer, inputs
    for line in longer:
        args = line["args"]
        assert isinstance(args, dict) and isinstance(args["s"], str) and len(args["s"]) > 3, line
    assert any(6 in numbers_of(line, "covered")[LEN_FILE] for line in longer), inputs


# follow-a-builtin-called-through-the-builtins-module-closes-the-compare-row
def test_closes_the_compare_row() -> None:
    lines = ACCEPTED.read_text().splitlines()[1:]
    targets = {json.loads(line)["target"] for line in lines if line.strip()}

    assert BUILTINS_LEN not in targets
    assert "targets.strs.nothing_to_fill::mod_empty" in targets
    assert "targets.strs.nothing_to_fill::format_empty" in targets


# follow-a-builtin-called-through-the-builtins-module-follows-the-other-spellings
@pytest.mark.parametrize(
    ("spelled", "bare", "seed"),
    [
        (f"{SPELLINGS}::code", f"{BARE}::code", '{"c": "b"}'),
        (f"{SPELLINGS}::sized", f"{BARE}::sized", '{"s": "ab"}'),
        (f"{SPELLINGS}::character", f"{BARE}::character", '{"n": 66}'),
        (f"{STAR}::code", f"{BARE}::code", '{"c": "b"}'),
    ],
    ids=["b.ord", "size", "chr", "star"],
)
def test_follows_the_other_spellings(spelled: str, bare: str, seed: str) -> None:
    result = run_pyct(spelled, seed)
    plain = run_pyct(bare, seed)

    assert result.returncode == plain.returncode == 0, result.stderr + plain.stderr
    inputs = input_lines(result.stdout)
    assert taken(inputs[0]) == taken(first_line(plain.stdout))
    assert taken(inputs[0]), inputs[0]
    assert inputs[0]["downgrades"] == []
    last = forks_of(inputs[0])[-1]
    file = str(last["file"])
    assert int(str(last["line"])) + 1 in union_of(inputs)[file]


# follow-a-builtin-called-through-the-builtins-module-leaves-a-name-bound-otherwise-as-written
@pytest.mark.parametrize(
    "target",
    ["targets.intercept.builtins_rebound::check", "targets.intercept.builtins_star_other::check"],
    ids=["assigned-in-a-function", "star-import-from-another-module"],
)
def test_leaves_a_name_bound_otherwise_as_written(target: str) -> None:
    result = run_pyct(target, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert named_downgrades(seed) == [("__len__", 1)]
    assert seed["forks"] == []


# follow-a-builtin-called-through-the-builtins-module-leaves-other-packages-as-written
def test_leaves_other_packages_as_written() -> None:
    # run from the folder that holds two top-level packages: shop, the target's, and measure
    result = run_pyct("shop.named::total", '{"s": "ab"}', cwd=SCOPE)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["downgrades"] == [downgrade("__len__", 1, "targets/scope/measure/named.py:5:7")]
    assert [fork for fork in forks_of(seed) if fork["line"] == 5] == []


# follow-a-builtin-called-through-the-builtins-module-leaves-a-raise-to-the-target
@pytest.mark.parametrize(
    ("target", "seed", "plain"),
    [
        ("sized", '{"n": 5}', lambda: len(5)),  # pyrefly: ignore[bad-argument-type]
        ("g", '{"x": -1}', lambda: chr(-1)),
    ],
    ids=["len", "chr"],
)
def test_leaves_a_raise_to_the_target(target: str, seed: str, plain: object) -> None:
    error = python_raise(plain)
    result = run_pyct(f"{RAISES}::{target}", seed)

    assert result.returncode == 0, result.stderr
    detail = f"{type(error).__name__}: {error}"
    assert first_line(result.stdout)["failure"] == {"kind": "target_raised", "detail": detail}
    assert "pyct bug" not in result.stderr, result.stderr
