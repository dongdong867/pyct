"""A run's loops in use: a formula's runner runs its code only in an input's own process, the run
puts each loop in core's table and takes out its own at its end, and a checked formula comes into
use only for inputs in a process of their own, a loop that cannot leave part way, and changed
values of the kinds a loop in use hands on."""

import ast
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.core.entry import in_use
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Changed, GoingIn, PieceRun, Site
from pyct.intercept.hook import Interception, intercepting
from pyct.run.formula_runner import FormulaInPyctProcessError, FormulaRunner, FormulaText
from pyct.run.isolation import Isolation
from pyct.run.loops_in_use import (
    IN_PYCT_S_PROCESS,
    LoopsInUse,
    leaving_by,
    unused_because,
)
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.summary_checks import CompleteRun, Formula, formula_code
from pyct.run.target import load_target
from tests.acceptance.harness import REPO_ROOT
from tests.unit.run.test_run_in_use import COUNTS, LOOP
from tests.unit.run.test_run_pieces import forget_modules

G = str(REPO_ROOT / "targets" / "summaries" / "loops.py")
FEW_Z, FEW_STOPS = Site(G, 45, 4), Site(G, 89, 4)
COUNT = 'def summary(s, t):\n    return {"t": t + s.count("z")}\n'
# the text a runner a test builds by hand carries
TEXT = FormulaText(COUNT, ("s", "t"), ("t",), (G, 45, 4), "<summary m:3:4>")


def compiled(text: str, file: str = "<summary m:3:4>") -> Formula:
    formula = formula_code(text, ("s", "t"), ("t",), file)
    assert isinstance(formula, Formula)
    return formula


def formula_at(site: Site, text: str = COUNT) -> tuple[FormulaText, types.CodeType]:
    """A formula of a loop at ``site``: its text, and its code as pyct's process compiles it."""
    file = "<summary m:3:4>"
    place = (site.file, site.line, site.col)
    formula = FormulaText(text, ("s", "t"), ("t",), place, file)
    return formula, compiled(text, file).code


@pytest.fixture
def table() -> Iterator[dict[tuple[str, int, int], LoopInUse]]:
    """Core's table of loops in use, empty for the test and after it."""
    in_use.IN_USE.clear()
    yield in_use.IN_USE
    in_use.IN_USE.clear()


def test_a_runner_built_here_never_runs_its_code_here() -> None:
    code = compile("raise SystemExit('ran')", "<summary m:3:4>", "exec")
    runner = FormulaRunner(code, TEXT)

    with pytest.raises(FormulaInPyctProcessError):
        runner({"s": "z", "t": 0})

    assert runner.summary is None


def test_a_loop_put_in_use_runs_nothing_and_takes_its_place_in_core_s_table(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    code = compile("raise SystemExit('ran')", "<summary m:3:4>", "exec")
    formula = FormulaText("", ("s", "t"), ("t",), (G, 45, 4), "<summary m:3:4>")
    loops = LoopsInUse()

    loops.use(formula, code)

    loop = table[(G, 45, 4)]
    assert (loop.parameters, loop.changed) == (("s", "t"), ("t",))
    assert isinstance(loop.formula, FormulaRunner)
    assert loop.formula.code is code
    assert loop.formula.summary is None
    assert loop.formula.text is formula
    assert loops.sites == {FEW_Z}


def test_closing_takes_out_the_run_s_own_loops_alone(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    other = LoopInUse(("s",), ("t",), lambda values: values)
    table[("other.py", 3, 4)] = other
    loops = LoopsInUse()
    loops.use(*formula_at(FEW_Z))

    loops.close()

    assert table == {("other.py", 3, 4): other}
    assert loops.sites == set()


@pytest.fixture
def counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """test_run_in_use's target as a package importable from the path, and its module file."""
    package = tmp_path / "formula_loops"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "counts.py").write_text(COUNTS)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "counts.py"
    forget_modules("formula_loops")


def test_a_forked_input_runs_the_compiled_formula_and_pyct_s_process_does_not(
    counts: Path, tmp_path: Path, table: dict[tuple[str, int, int], LoopInUse]
) -> None:
    loops = LoopsInUse()
    loops.use(*formula_at(Site(str(counts), *LOOP)))
    runner = table[(str(counts), *LOOP)].formula
    assert isinstance(runner, FormulaRunner)
    interception = Interception(module="formula_loops.counts", cache=tmp_path / "c", pieces=True)

    with intercepting(interception):
        result = run(
            load_target("formula_loops.counts::f"),
            {"s": "az"},
            limits=Limits(budget=Budget(seconds=60)),
            setup=Setup(isolation=Isolation.FORK),
        )

    condition = [">", ["+", 0, ["count", "s", "'z'"]], 1]
    assert [[fork.expression for fork in record.forks] for record in result.records] == [
        [condition],
        [condition],
    ]
    assert runner.summary is None


def complete(*changed: str) -> tuple[CompleteRun, ...]:
    """A complete run of a loop for each value of ``t`` written as JSON text."""
    going_in = (GoingIn("s", '"ab"', True),)
    return tuple(
        CompleteRun(1, PieceRun(FEW_Z, going_in, (Changed("t", each),))) for each in changed
    )


def test_a_formula_for_inputs_in_pyct_s_process_is_not_used() -> None:
    assert unused_because(FEW_Z, complete("0"), ("t",), isolated=False) == IN_PYCT_S_PROCESS


def test_a_formula_for_a_loop_that_returns_is_not_used() -> None:
    assert unused_because(FEW_STOPS, complete("0"), ("t",), True) == "the loop holds a return"


@pytest.mark.parametrize("value", ["0", "1.5", '"z"', "true", "NaN"])
def test_a_formula_whose_loop_changes_an_int_float_str_or_bool_is_used(value: str) -> None:
    assert unused_because(FEW_Z, complete("0", value), ("t",), True) is None


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("[1]", "t is a list"),
        ('{"a": 1}', "t is a dict"),
        ("null", "t is None"),
        ("{", "t is unreadable"),
    ],
)
def test_a_formula_whose_loop_changes_a_value_of_another_kind_is_not_used(
    value: str, reason: str
) -> None:
    assert unused_because(FEW_Z, complete("0", value), ("t",), True) == reason


@pytest.mark.parametrize(
    ("function", "reason"),
    [
        ("def f(s):\n    t = 0\n    for c in s:\n        yield c\n        t += 1\n", "a yield"),
        (
            "async def f(s):\n    t = 0\n    for c in s:\n        await c\n        t += 1\n",
            "an await",
        ),
    ],
)
def test_a_formula_for_a_loop_that_yields_or_awaits_is_not_used(
    tmp_path: Path, function: str, reason: str
) -> None:
    module = tmp_path / "m.py"
    module.write_text(f"{function}    return t\n")
    loop = Site(str(module), 3, 4)

    assert unused_because(loop, complete("0"), ("t",), True) == f"the loop holds {reason}"


def test_a_formula_whose_loop_is_gone_from_its_file_is_not_used() -> None:
    gone = Site(G, 1, 0)
    assert unused_because(gone, complete("0"), ("t",), True) == "the loop's file no longer holds it"


def statement(code: str) -> ast.stmt:
    """The first statement of the function ``code`` defines."""
    function = ast.parse(code).body[0]
    assert isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
    return function.body[0]


@pytest.mark.parametrize(
    ("code", "leaving"),
    [
        ("def f(s):\n    for c in s:\n        return c\n", "a return"),
        ("def f(s):\n    while s:\n        yield s\n", "a yield"),
        ("def f(s):\n    for c in s:\n        yield from c\n", "a yield"),
        ("async def f(s):\n    for c in s:\n        await c\n", "an await"),
        ("async def f(s):\n    async for c in s:\n        pass\n", "an await"),
        ("async def f(s):\n    t = [c async for c in s]\n", "an await"),
        ("def f(s):\n    while (yield s):\n        pass\n", "a yield"),
        ("def f(s):\n    for c in s:\n        pass\n    else:\n        return s\n", None),
        ("def f(s):\n    for c in s:\n        def g():\n            return c\n", None),
        ("def f(s):\n    for c in s:\n        g = lambda: (yield c)\n", None),
        (
            "def f(s):\n    for c in s:\n        class K:\n            def m(self):\n"
            "                return c\n",
            None,
        ),
        ("def f(s):\n    t = [c for c in s]\n", None),
    ],
    ids=[
        "return",
        "yield",
        "yield from",
        "await",
        "async for",
        "async comprehension",
        "yield in a while's test",
        "return in the else",
        "nested function",
        "lambda",
        "class",
        "comprehension",
    ],
)
def test_what_a_loop_holds_that_leaves_its_frame(code: str, leaving: str | None) -> None:
    assert leaving_by(statement(code)) == leaving


def test_a_runner_is_called_on_values_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = FormulaRunner(compiled(COUNT).code, TEXT)
    # as in an input's own process, whose id is not the one that built the runner
    monkeypatch.setattr(runner, "home", -1)

    assert runner({"s": "zaz", "t": 1}) == {"t": 3}
    assert runner.summary is not None
