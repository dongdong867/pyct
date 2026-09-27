"""Acceptance tests for wrap-builtin-functions-in-the-target: `len`, `ord` and `chr` bound.

Each test spawns ``python -P -m pyct`` through the harness. pyct binds the three names in
every module of the target's top-level package as Python imports it, so only a run through
the command line proves the binding holds where the target runs.
"""

import re

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct, summary_line
from tests.acceptance.test_bools import expressions, failure_of, sides
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_strs import text
from tests.acceptance.test_substitute_is_and_in import compiled_total, covered_of, plain_lines

INTERCEPT = REPO_ROOT / "targets" / "intercept"
SIZED = "targets.intercept.sized::check"
SIZED_FILE = INTERCEPT / "sized.py"
CODES = "targets.intercept.codes"
SIZED_ACROSS = "targets.intercept.sized_across::spread"
HANDED_ON = "targets.intercept.handed_on::pair"
PLAIN_BUILTINS = "targets.intercept.plain_builtins::plain"
OWN_LEN = "targets.intercept.own_len::check"
BUILTINS_LEN = "targets.intercept.builtins_len::check"
THREADED_SIZED = "targets.intercept.threaded_sized::check"
TYPE_NAMES = "targets.intercept.type_names::f"
REFUSALS = "targets.intercept.refusals"
SCOPE = REPO_ROOT / "targets" / "scope"
LONGER = [">", ["len", "s"], 3]


def downgrade_names(line: dict[str, object]) -> list[object]:
    """The name of each downgrade on a printed line, in the order the input met them."""
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [downgrade["name"] for downgrade in downgrades]


def raised(line: dict[str, object], error: str) -> bool:
    """Whether the line says the target raised this exception."""
    failure = failure_of(line)
    return failure["kind"] == "target_raised" and str(failure["detail"]).startswith(f"{error}:")


# intercept-builtin-functions-follows-len
def test_follows_len() -> None:
    result = run_pyct(SIZED, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (LONGER, False)
    ]
    assert inputs[0]["downgrades"] == []
    assert f"fork {SIZED_FILE}:5:7  len(s) > 3  not taken" in result.stderr.splitlines()
    solved = [line for line in inputs[1:] if sides([line], LONGER) == {True}]
    assert solved, inputs
    assert all(len(text(line, "s")) > 3 for line in solved)
    covered = {number for line in inputs for number in covered_of(line, SIZED_FILE)}
    assert covered == {2, 3, 5, 6, 7}


# intercept-builtin-functions-follows-ord-and-chr
def test_follows_ord_and_chr() -> None:
    result = run_pyct(f"{CODES}::codes", '{"c": "a", "n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    compares = [e for e in expressions(inputs[0]) if isinstance(e, list) and e[0] == "=="]
    assert ["==", ["ord", "c"], 65] in compares
    assert ["==", ["chr", "n"], "'z'"] in expressions(inputs[1]) + expressions(inputs[0])
    assert any(text(line, "c") == "A" for line in inputs[1:]), inputs
    assert any(argument(line, "n") == 122 for line in inputs[1:]), inputs
    assert all(line["downgrades"] == [] for line in inputs)


# intercept-builtin-functions-follows-len-across-the-package
def test_follows_len_across_the_package() -> None:
    result = run_pyct(SIZED_ACROSS, '{"s": ""}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    target = str(INTERCEPT / "sized_across.py")
    assert [(fork["file"], fork["line"], fork["expression"]) for fork in forks_of(seed)] == [
        (str(INTERCEPT / "sized_helper.py"), 2, LONGER),
        (target, 6, [">", ["len", "s"], 4]),
        (target, 13, [">", ["len", "s"], 5]),
    ]
    assert all("__len__" not in downgrade_names(line) for line in input_lines(result.stdout))


# intercept-builtin-functions-follows-len-handed-on
def test_follows_len_handed_on() -> None:
    result = run_pyct(HANDED_ON, '{"s": "", "t": ""}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    pair = [">", ["+", ["len", "s"], ["len", "t"]], 5]
    assert expressions(inputs[0]) == [pair, LONGER]
    assert sides(inputs, pair) == {True, False}
    assert sides(inputs, LONGER) == {True, False}


# intercept-builtin-functions-keeps-positions-and-coverage
def test_keeps_positions_and_coverage() -> None:
    result = run_pyct(SIZED, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["line"], fork["col"]) for fork in forks_of(inputs[0])] == [(5, 7)]
    for line in inputs:
        assert covered_of(line, SIZED_FILE) == plain_lines(SIZED_FILE, "check", text(line, "s"))
    total = summary_line(result.stdout)["total"]
    assert total == {str(SIZED_FILE): compiled_total(SIZED_FILE)}


# intercept-builtin-functions-names-its-home-in-the-layout
def test_names_its_home_in_the_layout() -> None:
    layout = (REPO_ROOT / "CLAUDE.md").read_text().split("```")[1]
    entries = dict(re.findall(r"├── (\w+)/\s+(.*?)(?=\n│   ├──|\n│   └──)", layout, re.S))
    assert "len" in entries["intercept"] and "`is True`" in entries["intercept"]
    assert "LLM source rewrite" in entries["rewrite"]
    assert not re.search(r"builtin|intercept|substitut|len", entries["rewrite"])


# intercept-builtin-functions-changes-no-plain-answer
def test_changes_no_plain_answer() -> None:
    result = run_pyct(PLAIN_BUILTINS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert covered_of(seed, INTERCEPT / "plain_builtins.py") == plain_lines(
        INTERCEPT / "plain_builtins.py", "plain", 0
    )
    assert expressions(seed) == [[">", "x", 0]]
    assert seed["downgrades"] == []


# intercept-builtin-functions-keeps-a-module-s-own-name
def test_keeps_a_module_s_own_name() -> None:
    result = run_pyct(OWN_LEN, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # the module's own `len` answers 7, so plain Python takes the true side
    file = INTERCEPT / "own_len.py"
    assert covered_of(seed, file) == plain_lines(file, "check", "ab")
    assert 7 in covered_of(seed, file)
    assert seed["forks"] == []
    assert seed["downgrades"] == []


# intercept-builtin-functions-names-the-loss-through-the-builtins-module
def test_names_the_loss_through_the_builtins_module() -> None:
    result = run_pyct(BUILTINS_LEN, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["downgrades"] == [{"name": "__len__", "count": 1}]
    assert seed["forks"] == []


# intercept-builtin-functions-leaves-other-packages-as-written
def test_leaves_other_packages_as_written() -> None:
    # run from the folder that holds two top-level packages: shop, the target's, and measure
    result = run_pyct("shop.sized::total", '{"s": "ab"}', cwd=SCOPE)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["downgrades"] == [{"name": "__len__", "count": 1}]
    assert seed["forks"] == []


# intercept-builtin-functions-holds-in-every-way-an-input-runs
def test_holds_in_every_way_an_input_runs() -> None:
    runs = {
        "forked": run_pyct(SIZED, '{"s": "ab"}'),
        "in process": run_pyct(SIZED, '{"s": "ab"}', "--in-process"),
        # the thread its import starts sends every input to a fresh interpreter
        "fresh": run_pyct(THREADED_SIZED, '{"s": "ab"}'),
    }
    for way, result in runs.items():
        assert result.returncode == 0, (way, result.stderr)
        seed = first_line(result.stdout)
        assert expressions(seed) == [LONGER], way
        assert seed["downgrades"] == [], way
    assert "fresh interpreter" in runs["fresh"].stderr


# intercept-builtin-functions-leaves-type-names-alone
def test_leaves_type_names_alone() -> None:
    result = run_pyct(TYPE_NAMES, '{"x": 1, "s": "a"}')

    assert result.returncode == 0, result.stderr
    file = INTERCEPT / "type_names.py"
    assert covered_of(first_line(result.stdout), file) == plain_lines(file, "f", 1, "a")
    assert covered_of(first_line(result.stdout), file) == [5, 6, 7, 8, 9, 10]

    refused = run_pyct(TYPE_NAMES, '{"x": "1", "s": "a"}')

    assert refused.returncode == 2
    assert "x" in refused.stderr


# intercept-builtin-functions-leaves-a-builtins-raise-to-the-target
def test_leaves_a_builtins_raise_to_the_target() -> None:
    for target, seed_text, error in (
        ("sized", '{"n": 5}', "TypeError"),
        ("below_zero", '{"x": 0}', "ValueError"),
    ):
        result = run_pyct(f"{REFUSALS}::{target}", seed_text)

        assert result.returncode == 0, result.stderr
        assert raised(first_line(result.stdout), error), result.stdout
        assert "pyct bug" not in result.stderr, result.stderr


# intercept-builtin-functions-leaves-a-raise-in-the-targets-own-code-to-the-target
def test_leaves_a_raise_in_the_targets_own_code_to_the_target() -> None:
    result = run_pyct(f"{REFUSALS}::crate", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert raised(first_line(result.stdout), "ZeroDivisionError"), result.stdout


# intercept-builtin-functions-finds-the-string-ord-refuses
def test_finds_the_string_ord_refuses() -> None:
    result = run_pyct(f"{CODES}::code_of", '{"c": "a"}')

    assert result.returncode == 0, result.stderr
    first, second = input_lines(result.stdout)[:2]
    single = ["==", ["len", "c"], 1]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(first)] == [
        (10, single, True)
    ]
    assert len(text(second, "c")) != 1
    assert raised(second, "TypeError"), second


# intercept-builtin-functions-finds-the-code-chr-refuses
def test_finds_the_code_chr_refuses() -> None:
    result = run_pyct(f"{CODES}::character_of", '{"n": 65}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (14, [">=", "n", 0], True),
        (14, ["<=", "n", 1114111], True),
    ]
    refused = [line for line in inputs[1:] if not 0 <= argument(line, "n") <= 1114111]
    assert any(argument(line, "n") < 0 for line in refused), inputs
    assert any(argument(line, "n") > 1114111 for line in refused), inputs
    assert all(raised(line, "ValueError") for line in refused), refused


def test_the_stderr_line_reads_each_call() -> None:
    result = run_pyct(f"{CODES}::codes", '{"c": "a", "n": 0}')

    assert result.returncode == 0, result.stderr
    file = INTERCEPT / "codes.py"
    lines = result.stderr.splitlines()
    assert f"fork {file}:2:7  len(c) == 1  taken" in lines
    assert f"fork {file}:2:7  ord(c) == 65  not taken" in lines
