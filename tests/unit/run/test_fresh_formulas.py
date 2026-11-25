"""A fresh interpreter gets the loss sites' formulas in use with its request, as text, compiles each
one itself through the compile and form check pyct's process uses, and fills core's table before
its input runs; its inputs then give the records forked inputs give."""

import os
import pickle
import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.core.entry import losses
from pyct.core.entry.in_use import CALLS_IN_USE, CallInUse
from pyct.execution.execute import ExecutionResult
from pyct.intercept.hook import Interception, intercepting
from pyct.intercept.model_code import Refused
from pyct.run.call_turns import CallsInUse
from pyct.run.formula_runner import (
    FormulaInPyctProcessError,
    FormulaRunner,
    FormulaText,
    handed_formulas,
    install,
)
from pyct.run.fresh import _request
from pyct.run.isolation import Inputs, Isolation
from pyct.run.summary_form import compiled_formula
from pyct.run.target import load_target

QUARTER = 'def summary(n):\n    return {"answer": n % 4}\n'
# a text the form check refuses: its function has the wrong name
REFUSED = 'def total(n):\n    return {"answer": n % 4}\n'
FILE = "<summary m:3:4>"
SHIFTS = """\
def f(n):
    k = pow(n, 1, 4)
    if k == 2:
        return 1
    return 0
"""
# the line and column of the loss site in `SHIFTS`, and the line of the condition after it
POW, AFTER = (2, 8), 3
# the condition after the site, as a fork's expression writes it with `QUARTER` in use
CONDITION = ["==", ["%", "n", 4], 2]


@pytest.fixture(autouse=True)
def calls() -> Iterator[dict[tuple[str, int, int], CallInUse]]:
    """Core's table of loss sites in use, empty for the test and after it."""
    CALLS_IN_USE.clear()
    yield CALLS_IN_USE
    CALLS_IN_USE.clear()


def call_text(place: tuple[str, int, int], text: str = QUARTER) -> FormulaText:
    return FormulaText(text, ("n",), ("answer",), place, FILE, "__pow__", ("n", None, None))


def compiled(text: FormulaText) -> types.CodeType:
    code = compiled_formula(text.text, text.parameters, text.changed, text.file)
    assert not isinstance(code, Refused)
    return code


def test_the_formulas_in_use_are_read_as_text_from_core_s_table(
    calls: dict[tuple[str, int, int], CallInUse],
) -> None:
    text = call_text(("calls.py", 11, 11))
    CallsInUse().use(text, compiled(text))

    assert handed_formulas() == (text,)
    # a table filled by hand with a call of another kind hands nothing on for it
    calls[("other.py", 3, 4)] = CallInUse("__pow__", ("n",), lambda values: values)
    assert handed_formulas() == (text,)


def test_a_loss_site_in_use_is_handed_as_text_with_its_name_and_positions() -> None:
    text = call_text(("calls.py", 11, 11))
    CallsInUse().use(text, compiled(text))

    target = load_target("targets.summaries.calls::shifted")
    with (
        _request(target.spec, target.file, {"n": 3}, None) as request,
        os.fdopen(os.dup(request), "rb") as handed,
    ):
        pickle.load(handed)
        pickle.load(handed)
        formulas = pickle.load(handed)

    assert formulas == (text,)


def test_each_loss_site_handed_over_is_compiled_into_core_s_table_of_sites(
    calls: dict[tuple[str, int, int], CallInUse],
) -> None:
    install((call_text(("a.py", 3, 4), REFUSED), call_text(("calls.py", 11, 11))))

    assert list(calls) == [("calls.py", 11, 11)]
    call = calls[("calls.py", 11, 11)]
    assert (call.name, call.positions) == ("__pow__", ("n", None, None))
    assert isinstance(call.formula, FormulaRunner)
    assert call.formula.code.co_filename == FILE
    # the fresh interpreter builds the runner and calls it, so the runner has no process to refuse
    assert call.formula.home is None
    assert call.formula({"n": 13}) == {"answer": 1}


def test_a_runner_told_pyct_s_process_refuses_to_run_there() -> None:
    text = call_text(("calls.py", 11, 11))
    runner = FormulaRunner(compiled(text), text, os.getpid())

    assert runner.home == os.getpid()
    with pytest.raises(FormulaInPyctProcessError):
        runner({"n": 3})


def test_a_loss_site_coming_into_use_or_handed_over_loads_core_s_module_of_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(losses, "load_calls_in_use", lambda: loaded.append("loaded"))
    text = call_text(("calls.py", 11, 11))

    CallsInUse().use(text, compiled(text))
    install((call_text(("calls.py", 12, 11)),))

    assert loaded == ["loaded", "loaded"]


@pytest.fixture
def shifts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """`SHIFTS` as a package importable from the path, and its module file."""
    package = tmp_path / "fresh_formulas"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "shifts.py").write_text(SHIFTS)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield package / "shifts.py"
    for name in [name for name in sys.modules if name.split(".")[0] == "fresh_formulas"]:
        del sys.modules[name]


def ran(isolation: Isolation, tmp_path: Path) -> ExecutionResult:
    """The input ``{"n": 3}`` of `SHIFTS`, its loss sites recorded, where ``isolation`` says."""
    interception = Interception(module="fresh_formulas.shifts", cache=tmp_path / "c")
    with intercepting(interception):
        inputs = Inputs(load_target("fresh_formulas.shifts::f"), isolation, losses=True)
        return inputs({"n": 3}, None)


def at_the_condition(result: ExecutionResult) -> list[object]:
    return [fork.expression for fork in result.branches if fork.site.line == AFTER]


def test_inputs_in_fresh_interpreters_give_the_records_forked_inputs_give(
    shifts: Path, tmp_path: Path
) -> None:
    text = call_text((str(shifts), *POW))
    CallsInUse().use(text, compiled(text))

    forked = ran(Isolation.FORK, tmp_path)
    fresh = ran(Isolation.FRESH, tmp_path)

    assert at_the_condition(fresh) == [CONDITION]
    assert (fresh.branches, fresh.lines, fresh.drops, fresh.failure) == (
        forked.branches,
        forked.lines,
        forked.drops,
        forked.failure,
    )


def test_a_fresh_input_gets_the_site_s_real_answer_when_its_formula_does_not_compile(
    shifts: Path, tmp_path: Path, calls: dict[tuple[str, int, int], CallInUse]
) -> None:
    place = (str(shifts), *POW)
    runner = FormulaRunner(compiled(call_text(place)), call_text(place, REFUSED), os.getpid())
    losses.load_calls_in_use()
    calls[place] = CallInUse("__pow__", ("n", None, None), runner)

    result = ran(Isolation.FRESH, tmp_path)

    assert result.failure is None
    assert (at_the_condition(result), result.drops) == ([], ())
    [lost] = [each for each in result.losses if (each.site.line, each.site.col) == POW]
    assert [each.value for each in lost.changed] == ["3"]
