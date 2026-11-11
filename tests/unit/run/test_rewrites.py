"""The rewrites tool in a run: a rewrite runs only in a forked child, an ask past the token limit
ends every later ask, and a kept rewrite whose ask gives no input leaves the plan's own ask."""

import json
import sys
import time

import pytest

from pyct.binding.bind import Seed
from pyct.branches.plan import plan
from pyct.core.foundation.branch import Branch, Site
from pyct.results.causes import Condition, Reason, WhyEntry
from pyct.results.coverage import Scope
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.rewrite.condition import rewrite_code
from pyct.run import loop as loop_module
from pyct.run import model_runs
from pyct.run import rewrites as rewrites_module
from pyct.run.loop import Solved
from pyct.run.process import InputStartError
from pyct.run.rewrites import Rewrites, _Child, _module_of
from pyct.run.stuck import Handled, Moment, Outcome
from pyct.run.target import Target, interception, load_target
from pyct.run.tell import Ask, Tell, Told
from pyct.solver.answer import Sat, Timeout, Unsat
from tests.acceptance.llm_rewrites import FakeRewrites, file_of, llm_said, run_rewrites

TEXT = "targets.rewrites.text::exponent"
COUNTED = "targets.rewrites.counted::exponent"


@pytest.fixture(autouse=True)
def _cache(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("PYCT_CACHE_DIR", str(tmp_path))


def loaded(spec: str) -> Target:
    """The target, its package substituted as a run's owner loads it, so a later run in this
    process meets the module as it would have loaded it."""
    with interception(spec):
        return load_target(spec)


def test_a_rewrite_beside_a_second_thread_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 2)
    provider = FakeRewrites(['s == "1e-30"'])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    at = f"llm: rewrite for {file_of('text')}:2:7"
    assert llm_said(ran.said) == [f'{at}: s == "1e-30"', f"{at} skipped: cannot fork"]
    assert len(provider.requests) == 1


def test_an_ask_past_the_token_limit_ends_every_later_ask_unsaid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    limit = Unanswered(Why.LIMIT, "token limit reached", AskCost(1))
    provider = FakeRewrites([limit])

    ran = run_rewrites(TEXT, {"s": "0"}, provider)

    assert llm_said(ran.said) == []
    assert len(provider.requests) == 1


def test_a_child_pyct_cannot_start_is_said_as_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_: object) -> object:
        raise InputStartError("no memory")

    monkeypatch.setattr(rewrites_module, "run_model", refused)
    code = rewrite_code("n > 0", ("n",), "<rewrite m:1:1>")

    ran = _Child(time.monotonic() + 1).run(code, {"n": 0})  # pyrefly: ignore[bad-argument-type]

    assert ran == "cannot start a child: no memory"


def test_the_place_names_the_module_by_its_dotted_name() -> None:
    target = loaded(TEXT)
    helper = sys.modules[json.__name__]

    assert _module_of(target.file, target) == "targets.rewrites.text"
    assert _module_of(str(helper.__file__), target) == "json"
    assert _module_of("/nowhere/lost.py", target) == "lost"


def kept_at_line_2() -> tuple[Rewrites, Site]:
    """The tool for COUNTED with `s == "1e-30"` kept for line 2's true side."""
    target = loaded(COUNTED)
    tool = Rewrites(FakeRewrites([]), target, Told(Scope.of_module(target.file), Tell()))
    site = Site(target.file, 2, 7)
    code = rewrite_code('s == "1e-30"', ("s", "n"), "<rewrite counted:2:7>")
    tool.kept.keep(Condition(site, True), code, ("s", "n"))  # pyrefly: ignore[bad-argument-type]
    return tool, site


def test_a_kept_rewrite_whose_ask_gives_no_input_leaves_the_plan_s_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    tool, site = kept_at_line_2()
    forks = (Branch(["==", ["float", "s"], 1e-30], True, site), Branch([">", "n", 0], True, site))
    wanted = plan(forks)
    assert wanted is not None
    held: list[object] = []

    def answered(wanted: object, origin: object, limit: float, asked: object = None) -> Solved:
        held.append(asked)
        answer = Unsat() if asked is not None else Sat({"s": "1e-30", "n": 1})
        return Solved(answer, 0.0, Ask(0, wanted.aim, 0, ()))  # type: ignore[attr-defined]

    monkeypatch.setattr(rewrites_module, "solver_answer", answered)
    monkeypatch.setattr(loop_module, "solver_answer", answered)

    solved = tool.solved(wanted, Seed.of({"s": "1e-30", "n": 0}), 5.0)

    assert isinstance(solved.answer, Sat)
    assert solved.source.value == "solver"
    assert held[0] is not None and held[1] is None


def test_a_kept_rewrite_whose_ask_used_the_limit_leaves_none_for_the_plan_s_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(model_runs, "running", lambda: 1)
    tool, site = kept_at_line_2()
    wanted = plan((Branch(["==", ["float", "s"], 1e-30], False, site),))
    assert wanted is not None

    def slow(wanted: object, origin: object, limit: float, asked: object = None) -> Solved:
        time.sleep(limit)
        return Solved(Unsat(), limit, Ask(0, wanted.aim, 0, ()))  # type: ignore[attr-defined]

    monkeypatch.setattr(rewrites_module, "solver_answer", slow)

    solved = tool.solved(wanted, Seed.of({"s": "0", "n": 0}), 0.2)

    assert isinstance(solved.answer, Timeout)
    # the plan's own ask never ran, so no plan is kept as one the solver gave up on
    assert tool.given_up == {}


def test_an_entry_with_no_plan_kept_for_its_condition_is_skipped() -> None:
    tool, site = kept_at_line_2()
    entry = WhyEntry(site.file, (3,), Reason.NOT_TAKEN, condition=Condition(site, False))

    handled = tool.take((entry,), Moment(1, (entry,), run=None))  # pyrefly: ignore[bad-argument-type]

    assert handled == Handled((Outcome.SKIPPED,), asked=False)
