"""A visit to a condition in a loop whose path already holds the same check on the other side: a
run with rewrites answers it unsat without the solver and keeps no plan for it, a run without
rewrites asks as before, and any other visit the solver gives up on is kept and asked about."""

import time
import types

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan, plan
from pyct.core.foundation.branch import Branch, Expression, Site
from pyct.results.causes import Condition, Reason, WhyEntry
from pyct.results.coverage import Scope
from pyct.rewrite.condition import Rewrite, rewrite_code
from pyct.run import loop as loop_module
from pyct.run import model_runs
from pyct.run import rewrites as rewrites_module
from pyct.run.loop import Asker, Solved
from pyct.run.rewrites import Rewrites
from pyct.run.stuck import Handled, Moment, Outcome
from pyct.run.target import Target, interception, load_target
from pyct.run.tell import Ask, Tell, Told
from pyct.solver.answer import Timeout, Unsat
from tests.acceptance.llm_rewrites import FakeRewrites
from tests.unit.rewrite.test_ask import chain

EACH = "targets.rewrites.visits::each"
CHANGING = "targets.rewrites.visits::changing"
FLOAT_S: Expression = ["==", ["float", "s"], 1e-30]


@pytest.fixture(autouse=True)
def asks(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> list[Plan]:
    """Each plan the solver was asked about, which gives up on every ask, with pyct's process
    on one thread and the target's substituted code in a cache folder of the test's own."""
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))
    asked: list[Plan] = []

    def gave_up(wanted: Plan, origin: object, limit: float, held: object = None) -> Solved:
        asked.append(wanted)
        return Solved(Timeout(), limit, Ask(0, wanted.aim, 0, ()))

    monkeypatch.setattr(loop_module, "solver_answer", gave_up)
    monkeypatch.setattr(rewrites_module, "solver_answer", gave_up)
    return asked


def tool_for(spec: str, provider: FakeRewrites) -> tuple[Rewrites, str]:
    """The tool for ``spec``, its package substituted as a run's owner loads it, and its file."""
    with interception(spec):
        target: Target = load_target(spec)
    return Rewrites(provider, target, Told(Scope.of_module(target.file), Tell())), target.file


def visits(site: Site, *checks: tuple[Expression, bool]) -> Plan:
    """The plan whose path takes each check at ``site`` in turn, the last flipped."""
    made = plan(tuple(Branch(expression, taken, site) for expression, taken in checks))
    assert made is not None
    return made


def picked(tool: Rewrites | Asker, wanted: Plan, args: dict[str, object]) -> Solved:
    """The answer for the pick of ``wanted``."""
    return tool.solved(wanted, Seed.of(args), 5.0)


def moment_at(site: Site, side: bool) -> tuple[WhyEntry, Moment]:
    """A stuck moment whose one entry is the condition at ``site`` and ``side``, in a run that
    goes on."""
    entry = WhyEntry(site.file, (4,), Reason.NOT_TAKEN, condition=Condition(site, side))
    bounds = types.SimpleNamespace(until=None, solver_timeout=1.0)
    going = types.SimpleNamespace(stopped=None, bounds=bounds, pause=lambda _seconds: None)
    return entry, Moment(1, (entry,), run=going)  # pyrefly: ignore[bad-argument-type]


# llm-rewrite-visit-an-input-can-meet-skips-a-visit-that-holds-its-own-check
@pytest.mark.parametrize("taken", [False, True])
def test_a_visit_whose_path_took_its_check_the_other_way_is_unsat_unasked(
    asks: list[Plan], taken: bool
) -> None:
    tool, file = tool_for(EACH, FakeRewrites([]))
    site = Site(file, 3, 21)
    again: Expression = ["==", ["float", "s"], 1e-30]
    started = time.monotonic()

    solved = picked(tool, visits(site, (FLOAT_S, taken), (again, taken)), {"s": "0", "items": [1]})

    assert isinstance(solved.answer, Unsat)
    assert solved.seconds < 0.1 and time.monotonic() - started < 0.1
    assert solved.asked.programs == ()
    assert asks == []
    assert tool.given_up == {}


# llm-rewrite-visit-an-input-can-meet-skips-a-visit-that-holds-its-own-check
def test_a_kept_rewrite_is_neither_run_nor_asked_for_a_visit_that_holds_its_check(
    asks: list[Plan], monkeypatch: pytest.MonkeyPatch
) -> None:
    tool, file = tool_for(EACH, FakeRewrites([]))
    site = Site(file, 3, 21)
    rewrite = rewrite_code('s == "1e-30"', ("s", "items"), "<rewrite visits:3:21>")
    assert isinstance(rewrite, Rewrite)
    tool.kept.keep(Condition(site, True), rewrite)
    ran: list[object] = []
    monkeypatch.setattr(rewrites_module._Child, "run", lambda *args: ran.append(args) or "no")

    solved = picked(
        tool, visits(site, (FLOAT_S, False), (FLOAT_S, False)), {"s": "0", "items": [1]}
    )

    assert isinstance(solved.answer, Unsat)
    assert ran == []
    assert asks == []


# llm-rewrite-visit-an-input-can-meet-skips-a-visit-that-holds-its-own-check
def test_a_stuck_moment_asks_nothing_about_a_condition_with_no_kept_visit() -> None:
    provider = FakeRewrites(["I cannot rewrite it."])
    tool, file = tool_for(EACH, provider)
    site = Site(file, 3, 21)
    picked(tool, visits(site, (FLOAT_S, False), (FLOAT_S, False)), {"s": "0", "items": [1]})
    entry, moment = moment_at(site, True)

    handled = tool.take((entry,), moment)

    assert handled == Handled((Outcome.SKIPPED,), asked=False)
    assert provider.requests == []


# llm-rewrite-visit-an-input-can-meet-leaves-a-run-without-rewrites-as-it-is
def test_a_run_without_rewrites_asks_the_solver_about_a_visit_that_holds_its_check(
    asks: list[Plan],
) -> None:
    site = Site("m.py", 3, 21)
    wanted = visits(site, (FLOAT_S, False), (FLOAT_S, False))

    solved = picked(Asker(), wanted, {"s": "0", "items": [1]})

    assert isinstance(solved.answer, Timeout)
    assert asks == [wanted]


# llm-rewrite-visit-an-input-can-meet-keeps-a-visit-of-a-changing-value
def test_a_visit_of_a_value_that_changed_is_asked_kept_and_asked_about(asks: list[Plan]) -> None:
    provider = FakeRewrites(["I cannot rewrite it."])
    tool, file = tool_for(CHANGING, provider)
    site = Site(file, 10, 11)
    first: Expression = ["==", ["float", ["[]", "items", 0]], 1e-30]
    second: Expression = ["==", ["float", ["[]", "items", 1]], 1e-30]
    wanted = visits(site, (first, False), (second, False))
    picked(tool, wanted, {"items": ["0", "0"]})
    entry, moment = moment_at(site, True)

    handled = tool.take((entry,), moment)

    assert asks == [wanted]
    assert tool.given_up[Condition(site, True)].plan is wanted
    assert handled.asked
    assert provider.requests[0].condition.text == "float(items[i]) == 1e-30"


# llm-rewrite-visit-an-input-can-meet-tells-literals-apart
@pytest.mark.parametrize(("one", "other"), [(1, 1.0), (1, True), (0.0, -0.0)])
def test_a_visit_whose_check_differs_in_a_literal_s_type_or_bits_is_asked_and_kept(
    asks: list[Plan], one: float, other: float
) -> None:
    tool, file = tool_for(EACH, FakeRewrites([]))
    site = Site(file, 3, 21)
    wanted = visits(site, (["==", "n", one], False), (["==", "n", other], False))

    picked(tool, wanted, {"s": "0", "items": [1, 2]})

    assert asks == [wanted]
    assert tool.given_up[Condition(site, True)].plan is wanted


# llm-rewrite-visit-an-input-can-meet-keeps-a-visit-past-the-compare-limit
def test_a_visit_pyct_cannot_compare_within_the_limit_is_asked_and_kept(asks: list[Plan]) -> None:
    tool, file = tool_for(EACH, FakeRewrites([]))
    site = Site(file, 3, 21)
    # each pass of the chain is 3 parts, so 40,000 passes are past the 100,000 a plan compares
    wanted = visits(site, (chain(40_000), False), (chain(40_000), False))

    picked(tool, wanted, {"s": "0", "items": [1, 2]})

    assert asks == [wanted]
    assert tool.given_up[Condition(site, True)].plan is wanted
