"""A fresh interpreter gets the formulas in use with its request, as text, compiles each one itself
through the compile and form check pyct's process uses, and fills core's table before its input
runs; its inputs then give the records forked inputs give."""

import os
import pickle
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.config.budget import Budget
from pyct.config.limits import Limits
from pyct.config.plateau import Plateau
from pyct.core.entry import in_use, losses
from pyct.core.entry.in_use import CALLS_IN_USE, CallInUse, LoopInUse
from pyct.core.foundation.branch import Site
from pyct.intercept.hook import Interception, intercepting
from pyct.intercept.model_code import Refused
from pyct.results.record import RunResult
from pyct.run.call_turns import CallsInUse
from pyct.run.formula_runner import (
    FormulaInPyctProcessError,
    FormulaRunner,
    FormulaText,
    handed_formulas,
    install,
)
from pyct.run.fresh import _request
from pyct.run.isolation import Isolation
from pyct.run.loops_in_use import LoopsInUse
from pyct.run.run import run
from pyct.run.setup import Setup
from pyct.run.summary_form import compiled_formula
from pyct.run.target import load_target
from tests.unit.run.test_loops_in_use import COUNT, FEW_Z, G, compiled, formula_at
from tests.unit.run.test_run_in_use import COUNTS, LOOP
from tests.unit.run.test_run_pieces import forget_modules

# a text the form check refuses: its function has the wrong name
REFUSED = 'def total(s, t):\n    return {"t": t + s.count("z")}\n'
FILE = "<summary m:3:4>"
# a run to its end, and one that stops 2 inputs after its last gain
WHOLE = Limits(budget=Budget(seconds=60))
SHORT = Limits(budget=Budget(seconds=20), plateau=Plateau(2))


@pytest.fixture(autouse=True)
def table() -> Iterator[dict[tuple[str, int, int], LoopInUse]]:
    """Core's table of loops in use, empty for the test and after it."""
    in_use.IN_USE.clear()
    yield in_use.IN_USE
    in_use.IN_USE.clear()


def text_of(place: tuple[str, int, int], text: str = COUNT) -> FormulaText:
    return FormulaText(text, ("s", "t"), ("t",), place, FILE)


def test_the_formulas_in_use_are_read_as_text_from_core_s_table() -> None:
    LoopsInUse().use(*formula_at(FEW_Z))

    assert handed_formulas() == (text_of((G, 45, 4)),)
    # a table filled by hand with a call of another kind hands nothing on for it
    in_use.IN_USE[("other.py", 3, 4)] = LoopInUse(("s",), ("t",), lambda values: values)
    assert handed_formulas() == (text_of((G, 45, 4)),)


def test_a_fresh_interpreter_s_request_carries_the_formulas_in_use() -> None:
    target = load_target("targets.summaries.loops::few_z")
    LoopsInUse().use(*formula_at(FEW_Z))

    with (
        _request(target.spec, target.file, {"s": "ab"}, None) as request,
        os.fdopen(os.dup(request), "rb") as handed,
    ):
        pickle.load(handed)
        pickle.load(handed)
        formulas = pickle.load(handed)

    assert formulas == (text_of((G, 45, 4)),)


def test_each_formula_handed_over_is_compiled_and_put_in_core_s_table(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    install((text_of((G, 45, 4)),))

    loop = table[(G, 45, 4)]
    assert (loop.parameters, loop.changed) == (("s", "t"), ("t",))
    assert isinstance(loop.formula, FormulaRunner)
    assert loop.formula.code.co_filename == FILE
    # the fresh interpreter builds the runner and calls it, so the runner has no process to refuse
    assert loop.formula.home is None
    assert loop.formula({"s": "zaz", "t": 1}) == {"t": 3}


def test_a_formula_that_does_not_compile_leaves_its_loop_out_of_core_s_table(
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    install((text_of(("a.py", 3, 4), REFUSED), text_of((G, 45, 4))))

    assert list(table) == [(G, 45, 4)]


def test_a_runner_told_pyct_s_process_refuses_to_run_there() -> None:
    runner = FormulaRunner(compiled(COUNT).code, text_of((G, 45, 4)), os.getpid())

    assert runner.home == os.getpid()
    with pytest.raises(FormulaInPyctProcessError):
        runner({"s": "z", "t": 0})


@pytest.fixture
def counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """test_run_in_use's target as a package importable from the path, and its module file."""
    package = tmp_path / "fresh_formulas"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "counts.py").write_text(COUNTS)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "counts.py"
    forget_modules("fresh_formulas")


def ran(isolation: Isolation, tmp_path: Path, limits: Limits = WHOLE) -> RunResult:
    interception = Interception(module="fresh_formulas.counts", cache=tmp_path / "c", pieces=True)
    with intercepting(interception):
        return run(
            load_target("fresh_formulas.counts::f"),
            {"s": "az"},
            limits=limits,
            setup=Setup(isolation=isolation),
        )


def records_of(result: RunResult) -> list[tuple[object, ...]]:
    return [
        (
            record.args,
            [(fork.expression, fork.site.line, fork.taken) for fork in record.forks],
            sorted(record.covered_lines),
            record.drops,
            record.failure,
        )
        for record in result.records
    ]


def test_inputs_in_fresh_interpreters_give_the_records_forked_inputs_give(
    counts: Path, tmp_path: Path
) -> None:
    LoopsInUse().use(*formula_at(Site(str(counts), *LOOP)))

    forked = ran(Isolation.FORK, tmp_path)
    fresh = ran(Isolation.FRESH, tmp_path)

    condition = [">", ["+", 0, ["count", "s", "'z'"]], 1]
    assert [[fork.expression for fork in record.forks] for record in fresh.records] == [
        [condition],
        [condition],
    ]
    assert records_of(fresh) == records_of(forked)


def test_a_fresh_input_runs_the_loop_as_written_when_its_formula_does_not_compile(
    counts: Path, tmp_path: Path
) -> None:
    # with no formula the loop's forks leave inputs open past any budget, so the runs stop early
    plain = ran(Isolation.FRESH, tmp_path, SHORT)
    place = (str(counts), *LOOP)
    runner = FormulaRunner(compiled(COUNT).code, text_of(place, REFUSED), os.getpid())
    in_use.IN_USE[place] = LoopInUse(("s", "t"), ("t",), runner)

    result = ran(Isolation.FRESH, tmp_path, SHORT)

    assert all(record.failure is None for record in result.records)
    # the seed's loop records its forks as it does with no formula, and the input drops nothing
    assert records_of(result)[0] == records_of(plain)[0]
    assert {fork.site.line for fork in result.records[0].forks} == {LOOP[0], LOOP[0] + 1}


QUARTER = 'def summary(n):\n    return {"answer": n % 4}\n'


def call_text(place: tuple[str, int, int], text: str = QUARTER) -> FormulaText:
    return FormulaText(text, ("n",), ("answer",), place, FILE, "__pow__", ("n", None, None))


@pytest.fixture
def calls() -> Iterator[dict[tuple[str, int, int], CallInUse]]:
    """Core's table of loss sites in use, empty for the test and after it."""
    CALLS_IN_USE.clear()
    yield CALLS_IN_USE
    CALLS_IN_USE.clear()


def test_a_loss_site_in_use_is_handed_as_text_with_its_name_and_positions(
    calls: dict[tuple[str, int, int], CallInUse],
) -> None:
    text = call_text(("calls.py", 11, 11))
    code = compiled_formula(text.text, text.parameters, text.changed, text.file)
    assert not isinstance(code, Refused)
    CallsInUse().use(text, code)

    target = load_target("targets.summaries.loops::few_z")
    with (
        _request(target.spec, target.file, {"s": "ab"}, None) as request,
        os.fdopen(os.dup(request), "rb") as handed,
    ):
        pickle.load(handed)
        pickle.load(handed)
        formulas = pickle.load(handed)

    assert formulas == (text,)


def test_each_loss_site_handed_over_is_compiled_into_core_s_table_of_sites(
    calls: dict[tuple[str, int, int], CallInUse],
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    install((call_text(("a.py", 3, 4), REFUSED), call_text(("calls.py", 11, 11))))

    assert table == {}
    assert list(calls) == [("calls.py", 11, 11)]
    call = calls[("calls.py", 11, 11)]
    assert (call.name, call.positions) == ("__pow__", ("n", None, None))
    assert isinstance(call.formula, FormulaRunner)
    assert call.formula.home is None
    assert call.formula({"n": 13}) == {"answer": 1}


def test_a_loss_site_coming_into_use_or_handed_over_loads_core_s_module_of_sites(
    monkeypatch: pytest.MonkeyPatch,
    calls: dict[tuple[str, int, int], CallInUse],
    table: dict[tuple[str, int, int], LoopInUse],
) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(losses, "load_calls_in_use", lambda: loaded.append("loaded"))
    text = call_text(("calls.py", 11, 11))
    code = compiled_formula(text.text, text.parameters, text.changed, text.file)
    assert not isinstance(code, Refused)

    CallsInUse().use(text, code)
    install((call_text(("calls.py", 12, 11)),))
    install((text_of((G, 45, 4)),))

    assert loaded == ["loaded", "loaded"]
