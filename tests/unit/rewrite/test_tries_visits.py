"""A condition's try on its kept visits: when the solver gives no input for the rewrite on one
visit, the same rewrite is tried on the next, with no new ask of the model; any other end of the
try tries no other visit. A later visit whose input the rewrite cannot be read on, raised or did
not finish on, records nothing for, or already meets is passed over; a rewrite pyct cannot run
there, or a budget spent as it ran, ends the tries. A try that gets no input fails once, with
each answer."""

import types
from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest

from pyct.binding.annotations import Builds, Check
from pyct.binding.bind import Seed
from pyct.branches.plan import Plan, plan
from pyct.core.foundation.branch import Branch, Fact, Site
from pyct.execution.execute import ExecutionResult
from pyct.llm.rewrites import EXACT_VALUE, request_text
from pyct.results.failure import Failure, FailureKind
from pyct.results.record import DowngradeCount, InputRecord, MissWhy
from pyct.rewrite.ask import GivenUp, Visit
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import RewriteSkipped, RewriteTook
from pyct.rewrite.tries import Asking, Tried
from pyct.solver.answer import Answer, Error, Sat, Timeout, Unknown, Unsat
from tests.unit.rewrite.orders import Order
from tests.unit.rewrite.test_tries import ABOUT, CONDITION, FORK, SITE, Fake, failed, own

GUARD = Site("m.py", 2, 4)


def visit_on(
    word: str, args: Mapping[str, object], checks: Mapping[str, Check] | None = None
) -> Visit:
    """A visit whose path took ``s.startswith(word)`` before the check, from ``args`` under the
    hints ``checks``."""
    guard = Branch(["startswith", "s", f"'{word}'"], True, GUARD)
    made = plan((guard, FORK))
    assert made is not None
    return Visit(made, Seed.of(dict(args), checks))


FIRST = visit_on("2", {"s": "2"})
SECOND = visit_on("1", {"s": "1"})
THIRD = visit_on("3", {"s": "3"})


@dataclass
class Visits(Fake):
    """The run around the tries, answering each solver ask in turn from ``answers``, the last
    again past the end, and running each rewrite as ``rans`` says for the input's ``s``."""

    answers: list[Answer | None] = field(default_factory=lambda: list[Answer | None]([Unsat()]))
    # each try asks whether the run goes on once for each visit, not once in all
    goes: list[bool] = field(default_factory=lambda: [True] * 40)
    rans: dict[object, ExecutionResult | str] = field(default_factory=dict)
    # the plan and the input of each solver ask, in order
    asked_on: list[tuple[Plan, Seed]] = field(default_factory=list)

    def ask(self, asked: tuple[Branch | Fact, ...], plan: Plan, origin: Seed) -> Answer | None:
        self.asks.append(asked)
        self.asked_on.append((plan, origin))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | str:
        ran = self.rans.get(args.get("s"))
        if ran is None:
            return super().run_rewrite(code, args)
        self.handed.append(dict(args))
        return ran


def tried_on(fake: Visits, *visits: Visit) -> Tried:
    """The tries on ``visits``, the first the one the request is about."""
    first, *later = visits
    given = GivenUp(CONDITION, first.plan, first.origin, MissWhy.TIMEOUT, tuple(later))
    return Asking(fake, given, ABOUT, ("s",), Kept()).tries(fake)


def asked_visits(fake: Visits) -> list[Visit]:
    return [Visit(plan, origin) for plan, origin in fake.asked_on]


def handed_s(fake: Visits) -> list[object]:
    return [args.get("s") for args in fake.handed]


def met_by_its_input() -> ExecutionResult:
    """A rewrite's run that records its own fork taken true: the input already meets it."""
    return ExecutionResult(frozenset(), (own(True),))


# llm-rewrite-visit-an-input-can-meet-tries-the-next-visit
@pytest.mark.parametrize("gave_none", [Unsat(), Unknown(), Timeout()])
def test_a_rewrite_with_no_input_on_one_visit_is_tried_on_the_next(gave_none: Answer) -> None:
    fake = Visits(answers=[gave_none, Sat({"s": "1e-30"})])

    assert tried_on(fake, FIRST, SECOND) == Tried(True, True)
    assert fake.asked == 1
    assert asked_visits(fake) == [FIRST, SECOND]
    assert handed_s(fake) == ["2", "1"]
    assert any(isinstance(note, RewriteTook) for note in fake.notes)
    assert failed(fake) == []


# llm-rewrite-visit-an-input-can-meet-fails-once-with-each-answer
def test_a_try_that_gets_no_input_on_each_visit_fails_once_with_each_answer() -> None:
    fake = Visits(answers=[Unsat(), Timeout(), Unsat()])

    tried_on(fake, FIRST, SECOND)

    assert failed(fake)[0] == "the solver answered unsat, then timeout"
    second = fake.requests[1]
    assert second.tries[0].solver_gave_up
    assert EXACT_VALUE in request_text(second)


# llm-rewrite-visit-an-input-can-meet-fails-once-with-each-answer
def test_a_try_on_one_visit_fails_as_it_did() -> None:
    fake = Visits(answers=[Unsat()])

    tried_on(fake, FIRST)

    assert failed(fake) == ["the solver answered unsat"] * 4
    assert not fake.requests[1].tries[0].solver_gave_up


# llm-rewrite-visit-an-input-can-meet-keeps-three-visits-at-most
def test_a_rewrite_is_tried_on_each_kept_visit_in_the_order_they_gave_up() -> None:
    fake = Visits(answers=[Unsat()])

    tried_on(fake, FIRST, SECOND, THIRD)

    assert asked_visits(fake)[:3] == [FIRST, SECOND, THIRD]
    assert failed(fake)[0] == "the solver answered unsat, then unsat, then unsat"


# llm-rewrite-visit-an-input-can-meet-tries-no-other-visit-after-another-failure
def test_an_input_that_took_the_other_side_tries_no_other_visit() -> None:
    other = InputRecord({"s": "2"}, (Branch(FORK.expression, False, SITE),), frozenset())
    fake = Visits(answers=[Sat({"s": "2"})], record=other)

    tried_on(fake, FIRST, SECOND)

    assert failed(fake)[0] == 'the input {"s": "2"} took the other side'
    assert asked_visits(fake)[0] == FIRST
    assert len(fake.asks) == 4


# llm-rewrite-visit-an-input-can-meet-tries-no-other-visit-after-another-failure
@pytest.mark.parametrize(
    ("ran", "reason"),
    [
        (
            ExecutionResult(frozenset(), (), failure=Failure(FailureKind.TARGET_RAISED, "boom")),
            "it raised on the input: boom",
        ),
        (met_by_its_input(), 'the input {"s": "2"} already meets it, yet took the other side'),
    ],
)
def test_a_rewrite_that_failed_before_its_ask_tries_no_other_visit(
    ran: ExecutionResult, reason: str
) -> None:
    fake = Visits(rans={"2": ran})

    tried_on(fake, FIRST, SECOND)

    assert failed(fake)[0] == reason
    assert fake.asked_on == []
    assert handed_s(fake)[:2] == ["2", "2"]


# llm-rewrite-visit-an-input-can-meet-tries-no-other-visit-after-another-failure
def test_a_solver_failure_on_a_later_visit_tries_no_other_visit() -> None:
    fake = Visits(answers=[Unsat(), Error("cvc5 crashed"), Unsat()])

    tried_on(fake, FIRST, SECOND, THIRD)

    assert failed(fake)[0] == "the solver failed: cvc5 crashed"
    assert asked_visits(fake)[:3] == [FIRST, SECOND, FIRST]


# llm-rewrite-visit-an-input-can-meet-passes-over-a-visit-it-cannot-run-on
@pytest.mark.parametrize(
    "second",
    [
        visit_on("1", {"t": "1"}),
        visit_on("1", {"s": {"__class__": "m::Order"}}),
        # llm-rewrite-hint-built-object-kept-only-where-the-input-holds-no-object
        visit_on("1", {"s": {"code": "1"}}, {"s": Builds(Order)}),
        visit_on("1", {"s": "raises"}),
        visit_on("1", {"s": "unfinished"}),
        visit_on("1", {"s": "downgraded"}),
        visit_on("1", {"s": "reads no argument"}),
        visit_on("1", {"s": "met"}),
    ],
)
def test_a_visit_the_rewrite_cannot_run_on_is_passed_over(second: Visit) -> None:
    raised = ExecutionResult(frozenset(), (), failure=Failure(FailureKind.TARGET_RAISED, "x"))
    unfinished = ExecutionResult(frozenset(), (), failure=Failure(FailureKind.TIMEOUT, "y"))
    lost = DowngradeCount("__float__", 1, Site("<rewrite m:2:7>", 3, 4))
    rans: dict[object, ExecutionResult | str] = {
        "raises": raised,
        "unfinished": unfinished,
        "downgraded": ExecutionResult(frozenset(), (), downgrades=(lost,)),
        "reads no argument": ExecutionResult(frozenset(), ()),
        "met": met_by_its_input(),
    }
    fake = Visits(answers=[Unsat(), Sat({"s": "1e-30"})], rans=rans)

    assert tried_on(fake, FIRST, second, THIRD) == Tried(True, True)
    assert asked_visits(fake) == [FIRST, THIRD]
    assert failed(fake) == []
    assert not any(isinstance(note, RewriteSkipped) for note in fake.notes)


# a rewrite pyct cannot run ends the condition's tries on any visit, said as skipped
# (decision llm-model-written-code-runs-only-in-a-forked-child-or-not-at-all)
@pytest.mark.parametrize("reason", ["cannot fork", "cannot start a child: no memory"])
def test_a_rewrite_pyct_cannot_run_on_a_later_visit_ends_the_tries_said(reason: str) -> None:
    fake = Visits(answers=[Unsat(), Sat({"s": "1e-30"})], rans={"1": reason})

    assert tried_on(fake, FIRST, SECOND, THIRD) == Tried(False, True, ended=reason)
    assert RewriteSkipped(SITE, reason) in fake.notes
    assert asked_visits(fake) == [FIRST]
    assert failed(fake) == []
    assert fake.asked == 1


# llm-rewrite-visit-an-input-can-meet-ends-at-the-budget
def test_a_budget_spent_during_one_visit_s_ask_asks_nothing_on_the_next() -> None:
    # going at the try's start and before the first visit's ask, then spent
    fake = Visits(answers=[Timeout(), Sat({"s": "1e-30"})], goes=[True, True, False])

    assert tried_on(fake, FIRST, SECOND) == Tried(False, True, ended="budget spent")
    assert asked_visits(fake) == [FIRST]
    assert handed_s(fake) == ["2"]
    assert failed(fake) == []


@dataclass
class SpentAsItRuns(Visits):
    """The run around the tries, whose budget runs out while the rewrite runs on ``spent_on``,
    which then does not finish."""

    spent_on: object = "1"
    spent: bool = False

    def going(self) -> bool:
        return not self.spent and super().going()

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | str:
        if args.get("s") != self.spent_on:
            return super().run_rewrite(code, args)
        self.spent = True
        self.handed.append(dict(args))
        return ExecutionResult(frozenset(), (), failure=Failure(FailureKind.TIMEOUT, "deadline"))


# llm-rewrite-visit-an-input-can-meet-ends-at-the-budget
def test_a_budget_spent_while_a_later_visit_s_rewrite_runs_ends_the_tries_unsaid() -> None:
    fake = SpentAsItRuns(answers=[Unsat(), Sat({"s": "1e-30"})])

    # the second visit is the last, so no visit after it checks the budget
    assert tried_on(fake, FIRST, SECOND) == Tried(False, True, ended="budget spent")
    assert asked_visits(fake) == [FIRST]
    assert handed_s(fake) == ["2", "1"]
    assert failed(fake) == []
