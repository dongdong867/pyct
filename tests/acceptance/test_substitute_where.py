"""Acceptance tests for substitute-is-and-literal-in-at-the-call-site: where substitution acts.

Which modules pyct substitutes, in which processes, what it leaves on disk, and what a
module that does not compile reports. Each test spawns ``python -P -m pyct`` through the
harness, some of them from a folder of their own.
"""

import subprocess
import sys
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, first_line, run_pyct
from tests.acceptance.test_bools import at, expressions
from tests.acceptance.test_ints import forks_of

INTERCEPT = REPO_ROOT / "targets" / "intercept"
ACROSS = "targets.intercept.across::spread"
IDENTITY = "targets.intercept.identity::check"
THREADED_IDENTITY = "targets.intercept.threaded_identity::check"
SCOPE = REPO_ROOT / "targets" / "scope"

# a package that holds one `is True`, written into a test's own folder
CHECK = 'def check(x: int) -> str:\n    b = x > 5\n    if b is True:\n        return "big"\n'
CHOOSE = (
    'def choose(x: int) -> str:\n    if x in {1, 5}:\n        return "picked"\n    return "other"\n'
)


def forks_at(line: dict[str, object]) -> list[tuple[str, int, object, object]]:
    """Each fork's file, line, expression and side, in the order the input met them."""
    return [
        (str(fork["file"]), int(str(fork["line"])), fork["expression"], fork["taken"])
        for fork in forks_of(line)
    ]


def files_under(folder: Path) -> dict[str, bytes]:
    """Every file under the folder, by its path relative to it, with its bytes."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


# intercept-builtin-functions-substitutes-across-the-package
def test_substitutes_across_the_package() -> None:
    result = run_pyct(ACROSS, '{"x": 10}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    target = str(INTERCEPT / "across.py")
    # the other module the target imports, the method, the nested function, and the module
    # the target imports only when it is called
    assert forks_at(seed) == [
        (str(INTERCEPT / "across_helper.py"), 2, [">", "x", 5], True),
        (target, 6, [">", "x", 5], True),
        (target, 15, [">", "x", 5], True),
        (str(INTERCEPT / "across_lazy.py"), 2, [">", "x", 5], True),
    ]


# intercept-builtin-functions-leaves-other-packages-unsubstituted
def test_leaves_other_packages_unsubstituted() -> None:
    # run from the folder that holds two top-level packages: shop, the target's, and measure
    result = run_pyct("shop.cart::total", '{"s": "x"}', cwd=SCOPE)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    probe = str(SCOPE / "measure" / "probe.py")
    # measure is Python's own: `in` makes its answer plain where it runs, on the `y =` line
    assert forks_at(seed) == [(probe, 2, ["in", "'a'", "s"], False)]
    assert at(seed, 3) == []


# intercept-builtin-functions-substitutes-in-every-way-an-input-runs
def test_substitutes_in_every_way_an_input_runs() -> None:
    runs = {
        "forked": run_pyct(IDENTITY, '{"x": 10}'),
        "in process": run_pyct(IDENTITY, '{"x": 10}', "--in-process"),
        # the thread its import starts sends every input to a fresh interpreter
        "fresh": run_pyct(THREADED_IDENTITY, '{"x": 10}'),
    }
    for way, result in runs.items():
        assert result.returncode == 0, (way, result.stderr)
        seed = first_line(result.stdout)
        assert [(line, expression, taken) for _, line, expression, taken in forks_at(seed)] == [
            (3 if way != "fresh" else 16, [">", "x", 5], True)
        ], way
    assert "fresh interpreter" in runs["fresh"].stderr


# intercept-builtin-functions-leaves-the-target-s-folder-as-it-was
def test_leaves_the_target_s_folder_as_it_was(tmp_path: Path) -> None:
    package = tmp_path / "tidy"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "check.py").write_text(CHECK)
    # plain Python imports it first, so its __pycache__ holds the bytecode Python wrote
    subprocess.run(
        [sys.executable, "-c", "import tidy.check"], cwd=tmp_path, check=True, timeout=30
    )
    before = files_under(package)
    assert any(name.startswith("__pycache__") for name in before), before

    # pyct keeps its cache where the variable does not name one: in the folder it runs from
    result = run_pyct("tidy.check::check", '{"x": 10}', cwd=tmp_path, unset=("PYCT_CACHE_DIR",))

    assert result.returncode == 0, result.stderr
    assert at(first_line(result.stdout), 3) == [[">", "x", 5]]
    assert files_under(package) == before
    assert (tmp_path / ".pyct_cache").is_dir()


# intercept-builtin-functions-substitutes-a-changed-file-again
def test_substitutes_a_changed_file_again(tmp_path: Path) -> None:
    module = tmp_path / "choose.py"
    module.write_text(CHOOSE)
    first = run_pyct("choose::choose", '{"x": 0}', cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert expressions(first_line(first.stdout)) == [["==", "x", 1], ["==", "x", 5]]

    # the same size, so only what the file holds tells the two apart
    module.write_text(CHOOSE.replace("{1, 5}", "{1, 7}"))
    again = run_pyct("choose::choose", '{"x": 0}', cwd=tmp_path)

    assert again.returncode == 0, again.stderr
    seed = first_line(again.stdout)
    assert expressions(seed) == [["==", "x", 1], ["==", "x", 7]]
    assert all(fork["taken"] is False for fork in forks_of(seed))


# intercept-builtin-functions-reports-a-module-that-does-not-compile
def test_reports_a_module_that_does_not_compile(tmp_path: Path) -> None:
    package = tmp_path / "shaky"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "entry.py").write_text(
        "from shaky import broken\n\n\ndef f(x: int) -> int:\n    return x\n"
    )
    (package / "broken.py").write_text("def g(:\n    return 1\n")

    result = run_pyct("shaky.entry::f", '{"x": 0}', cwd=tmp_path)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("cannot import shaky.entry: SyntaxError(")
    assert f"'{package / 'broken.py'}', 1," in result.stderr
