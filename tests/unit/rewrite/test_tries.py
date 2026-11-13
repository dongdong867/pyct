"""One condition's tries end early on an ask with no answer, a rewrite that cannot run, a spent
budget or an input that met the run's stop, and fail with a reason for each other miss."""

import types
from collections.abc import Mapping
from dataclasses import dataclass, field

from pyct.binding.bind import Seed
from pyct.branches.plan import Plan, plan
from pyct.core.foundation.branch import Branch, Fact, Site
from pyct.execution.execute import ExecutionResult
from pyct.results.causes import Condition
from pyct.results.failure import Failure, FailureKind
from pyct.results.llm_asks import AskCost, Unanswered, Why
from pyct.results.record import InputRecord, MissWhy, Stop, StopKind
from pyct.rewrite import tries
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.condition import HELD_COL, HELD_LINE, rewrite_code
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import RewriteFailed, RewriteNote, RewriteRead, RewriteSkipped
from pyct.rewrite.provider import RewriteReply, RewriteRequest
from pyct.rewrite.request import About
from pyct.rewrite.tries import Asking, Tried
from pyct.solver.answer import Answer, Error, Sat

SITE = Site("m.py", 2, 7)
CONDITION = Condition(SITE, True)
FORK = Branch(["==", ["float", "s"], 1e-30], False, SITE)
PLAN = plan((FORK,))
assert PLAN is not None
GIVEN = GivenUp(CONDITION, PLAN, Seed.of({"s": "0"}), MissWhy.TIMEOUT)
ABOUT = About("m:2:7", "def f(s):\n    ...")
FILE = "<rewrite m:2:7>"


def own(taken: bool) -> Branch:
    return Branch(["==", "s", "'1e-30'"], taken, Site(FILE, HELD_LINE, HELD_COL))


@dataclass
class Fake:
    """A provider answering ``reply`` and the run around the tries, each part as given."""

    reply: str | Unanswered = 's == "1e-30"'
    # None runs each rewrite as recording its own fork, in its own file, on the other side
    ran: ExecutionResult | str | None = None
    record: InputRecord | Stop = field(
        default_factory=lambda: InputRecord(
            {"s": "1e-30"}, (Branch(FORK.expression, True, SITE),), frozenset()
        )
    )
    goes: list[bool] = field(default_factory=lambda: [True] * 10)
    # why no rewrite can run at each ask, None when one can
    blocks: list[str | None] = field(default_factory=lambda: list[str | None]([None] * 10))
    answer: Answer | None = field(default_factory=lambda: Sat({"s": "1e-30"}))
    asks: list[tuple[object, ...]] = field(default_factory=list)
    notes: list[RewriteNote] = field(default_factory=list)
    asked: int = 0

    def rewrite(self, request: RewriteRequest) -> RewriteReply | Unanswered:
        self.asked += 1
        if isinstance(self.reply, Unanswered):
            return self.reply
        return RewriteReply(self.reply, AskCost(self.asked))

    def going(self) -> bool:
        return self.goes.pop(0)

    def blocked(self) -> str | None:
        return self.blocks.pop(0)

    def ask(self, asked: tuple[Branch | Fact, ...], plan: Plan, origin: Seed) -> Answer | None:
        self.asks.append(asked)
        return self.answer

    def pause(self, seconds: float) -> None:
        pass

    def note(self, note: RewriteNote) -> None:
        self.notes.append(note)

    def run_rewrite(
        self, code: types.CodeType, args: Mapping[str, object]
    ) -> ExecutionResult | str:
        if self.ran is None:
            fork = Branch(
                ["==", "s", "'1e-30'"], False, Site(code.co_filename, HELD_LINE, HELD_COL)
            )
            return ExecutionResult(frozenset(), (fork,))
        return self.ran

    def run_input(self, seed: Seed, plan: Plan) -> InputRecord | Stop:
        return self.record


def tried(fake: Fake) -> Tried:
    return Asking(fake, GIVEN, ABOUT, ("s",), Kept()).tries(fake)


def failed(fake: Fake) -> list[str]:
    return [note.reason for note in fake.notes if isinstance(note, RewriteFailed)]


def test_an_input_that_takes_the_side_ends_the_tries_with_the_rewrite_kept() -> None:
    fake = Fake()

    assert tried(fake) == Tried(True, True)
    assert fake.asked == 1


def test_an_ask_with_no_answer_ends_the_tries() -> None:
    skipped = Unanswered(Why.TIMED_OUT, "timed out", AskCost(1))
    fake = Fake(reply=skipped)

    assert tried(fake) == Tried(False, True, unanswered=skipped)


def test_no_try_starts_once_the_run_stops_going() -> None:
    fake = Fake(goes=[False])

    assert tried(fake) == Tried(False, False)
    assert fake.asked == 0


def test_a_rewrite_that_cannot_run_ends_the_tries_and_says_so() -> None:
    fake = Fake(ran="cannot fork")

    assert tried(fake) == Tried(False, True, ended="cannot fork")
    assert fake.notes == [RewriteRead(SITE, 's == "1e-30"'), RewriteSkipped(SITE, "cannot fork")]


def test_a_rewrite_that_cannot_run_ends_the_tries_before_any_ask() -> None:
    fake = Fake(blocks=["cannot fork"])

    assert tried(fake) == Tried(False, False, ended="cannot fork")
    assert fake.asked == 0
    assert fake.notes == [RewriteSkipped(SITE, "cannot fork")]


def test_a_rewrite_that_cannot_run_by_the_next_ask_ends_the_tries_unasked() -> None:
    fake = Fake(reply="no rewrite", blocks=[None, "cannot fork"])

    assert tried(fake) == Tried(False, True, ended="cannot fork")
    assert fake.asked == 1
    assert fake.notes[-1] == RewriteSkipped(SITE, "cannot fork")


def test_a_budget_spent_before_the_solver_asks_ends_the_tries() -> None:
    fake = Fake(goes=[True, False])

    assert tried(fake) == Tried(False, True, ended="budget spent")


def test_an_input_that_met_the_run_s_stop_ends_the_tries() -> None:
    fake = Fake(record=Stop(StopKind.BUDGET))

    assert tried(fake) == Tried(False, True, ended="budget spent")


def test_a_rewrite_that_raised_or_did_not_finish_fails_with_python_s_words() -> None:
    raised = Failure(FailureKind.TARGET_RAISED, "IndexError: string index out of range")
    fake = Fake(ran=ExecutionResult(frozenset(), (), failure=raised))
    tried(fake)
    timed_out = Fake(
        ran=ExecutionResult(frozenset(), (), failure=Failure(FailureKind.TIMEOUT, "past 5 s"))
    )
    tried(timed_out)

    assert failed(fake)[0] == "it raised on the input: IndexError: string index out of range"
    assert failed(timed_out)[0] == "it did not finish on the input: past 5 s"


def test_a_rewrite_the_input_already_meets_fails() -> None:
    fake = Fake(ran=ExecutionResult(frozenset(), (own(True),)))

    tried(fake)

    assert failed(fake) == ['the input {"s": "0"} already meets it, yet took the other side'] * 4


def test_a_rewrite_with_no_fork_of_its_own_and_no_downgrade_reads_no_argument() -> None:
    fake = Fake(ran=ExecutionResult(frozenset(), ()))

    tried(fake)

    assert failed(fake)[0] == "it reads no argument"


def test_a_solver_that_fails_on_a_rewrite_fails_the_try() -> None:
    fake = Fake(answer=Error("cvc5 said no"))

    tried(fake)

    assert failed(fake)[0] == "the solver failed: cvc5 said no"


def test_a_reply_with_no_expression_is_quoted_cut_in_the_next_ask() -> None:
    fake = Fake(reply="prose " * 100)
    requests: list[RewriteRequest] = []
    answer = fake.rewrite

    def kept(request: RewriteRequest) -> RewriteReply | Unanswered:
        requests.append(request)
        return answer(request)

    fake.rewrite = kept  # type: ignore[method-assign]
    tried(fake)

    earlier = requests[1].tries[0]
    assert len(earlier.rewrite) == tries.QUOTED
    assert earlier.reason == "the reply holds no expression"


def test_an_input_json_cannot_write_is_said_as_python_writes_it() -> None:
    assert tries._written({"o": frozenset({1})}) == "{'o': frozenset({1})}"


def test_a_try_with_no_time_left_for_its_ask_ends_the_tries() -> None:
    fake = Fake(answer=None)

    assert tried(fake) == Tried(False, True, ended="budget spent")
    assert len(fake.asks) == 1


def test_the_try_s_ask_holds_the_rewrite_s_own_fork_in_the_condition_s_place() -> None:
    fake = Fake()

    tried(fake)

    [asked] = fake.asks
    assert asked[-1] == Branch(["==", "s", "'1e-30'"], True, Site(FILE, HELD_LINE, HELD_COL))
    assert FORK not in asked


def test_a_try_s_ask_holds_the_kept_rewrite_of_an_earlier_condition_in_its_place() -> None:
    earlier = Branch(["==", ["float", "t"], 2.5], True, Site("m.py", 1, 7))
    wanted = plan((earlier, FORK))
    assert wanted is not None
    given = GivenUp(CONDITION, wanted, Seed.of({"s": "0", "t": "2.5"}), MissWhy.TIMEOUT)
    kept = Kept()
    code = rewrite_code('t == "2.5"', ("s", "t"), "<rewrite m:1:7>")
    assert isinstance(code, types.CodeType)
    kept.keep(Condition(earlier.site, True), code, ("s", "t"))
    fake = Fake()

    Asking(fake, given, ABOUT, ("s", "t"), kept).tries(fake)

    [asked] = fake.asks
    assert earlier not in asked
    sites = [item.site for item in asked if isinstance(item, Branch)]
    assert Site("<rewrite m:1:7>", HELD_LINE, HELD_COL) in sites
