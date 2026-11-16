"""One condition's tries on an input whose arguments are or hold objects: an object is read only as
``name.field``, a parameter that holds one inside a list, tuple or dict is not read at all, and a
condition with nothing left to read is given up unasked."""

from pyct.binding.annotations import Builds, Items
from pyct.binding.bind import Seed
from pyct.branches.plan import Plan
from pyct.execution.execute import ExecutionResult
from pyct.results.record import MissWhy
from pyct.rewrite.ask import GivenUp, Unread
from pyct.rewrite.kept import Kept
from pyct.rewrite.notes import RewriteGivenUp
from pyct.rewrite.tries import Asking, Tried
from pyct.solver.answer import Sat
from tests.unit.rewrite.orders import Order
from tests.unit.rewrite.test_tries import ABOUT, CONDITION, SITE, Fake, failed, own
from tests.unit.rewrite.test_tries import PLAN as MAYBE_PLAN

assert MAYBE_PLAN is not None
PLAN: Plan = MAYBE_PLAN


def test_an_input_whose_every_argument_holds_an_object_gives_up_before_any_ask() -> None:
    origin = Seed.of({"m": {"k": {"__class__": "m::Order"}}, "l": [{"__class__": "m::Order"}]})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake()

    found = Asking(fake, given, ABOUT, ("m", "l"), Kept()).tries(fake)

    assert found == Tried(False, False)
    assert fake.asked == 0
    assert fake.notes == [RewriteGivenUp(SITE, "no argument a rewrite may read")]


# llm-rewrite-object-fields-reads-self
def test_a_method_that_takes_only_self_is_asked_and_reads_its_field() -> None:
    given = GivenUp(CONDITION, PLAN, Seed.of({"self": {"code": "0"}}), MissWhy.TIMEOUT)
    kept = Kept("self")
    fake = Fake(reply='self.code == "1e-30"', answer=Sat({}))

    found = Asking(fake, given, ABOUT, ("self",), kept).tries(fake)

    assert found == Tried(True, True)
    assert fake.handed == [{"self": {"code": "0"}}]
    assert kept.rewrites[CONDITION].fields == ("self.code",)


def test_a_rewrite_reading_an_argument_that_holds_an_object_fails_and_is_named_in_the_ask() -> None:
    origin = Seed.of({"s": "0", "o": [{"__class__": "m::Order"}]})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake(reply="o[0].cancel() == 1")

    Asking(fake, given, ABOUT, ("s", "o"), Kept()).tries(fake)

    assert failed(fake) == ["a rewrite may not read o, which holds an object"] * 4
    assert [request.holders for request in fake.requests] == [("o",)] * 4
    assert fake.handed == []


# llm-rewrite-object-fields-refused-a-method-call
def test_a_rewrite_calling_a_method_of_an_object_fails_and_nothing_runs() -> None:
    origin = Seed.of({"s": "0", "o": {"__class__": "m::Order"}})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake(reply="o.cancel() == 1")

    Asking(fake, given, ABOUT, ("s", "o"), Kept()).tries(fake)

    assert failed(fake) == ["a rewrite may not call a method of o"] * 4
    assert [request.holders for request in fake.requests] == [()] * 4
    assert fake.handed == []


# llm-rewrite-object-fields-reads-a-seed-named-object
def test_a_condition_whose_only_argument_is_an_object_is_asked_and_reads_its_field() -> None:
    form = {"__class__": "m::Order", "code": "0"}
    given = GivenUp(CONDITION, PLAN, Seed.of({"o": form}), MissWhy.TIMEOUT)
    kept = Kept()
    fake = Fake(reply='o.code == "1e-30"', answer=Sat({}))

    assert Asking(fake, given, ABOUT, ("o",), kept).tries(fake) == Tried(True, True)
    assert fake.handed == [{"o": form}]
    assert kept.rewrites[CONDITION].fields == ("o.code",)


# llm-rewrite-object-fields-unread-a-property
def test_a_field_the_reader_reads_nothing_of_fails_the_try_with_its_reason() -> None:
    given = GivenUp(CONDITION, PLAN, Seed.of({"o": {"__class__": "m::Order"}}), MissWhy.TIMEOUT)
    reason = "it cannot read o.code: the class reads it with code"
    fake = Fake(reply='o.code == "1e-30"', ran=Unread(reason))

    found = Asking(fake, given, ABOUT, ("o",), Kept()).tries(fake)

    assert found == Tried(False, True)
    assert failed(fake) == [reason] * 4


def test_a_rewrite_beside_an_object_it_does_not_read_is_handed_none_of_it() -> None:
    origin = Seed.of({"s": "0", "o": {"__class__": "m::Order"}})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake()

    assert Asking(fake, given, ABOUT, ("s", "o"), Kept()).tries(fake) == Tried(True, True)
    assert fake.handed == [{"s": "0"}]


# llm-rewrite-hint-built-object-in-a-list-is-not-read
def test_an_input_whose_every_argument_a_hint_builds_gives_up_before_any_ask() -> None:
    checks = {"l": Items(list, Builds(Order), fixed=True)}
    origin = Seed.of({"l": [{"code": "0"}]}, checks)
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake()

    found = Asking(fake, given, ABOUT, ("l",), Kept()).tries(fake)

    assert found == Tried(False, False)
    assert fake.asked == 0
    assert fake.notes == [RewriteGivenUp(SITE, "no argument a rewrite may read")]


# llm-rewrite-object-fields-refused-a-hinted-object-s-key
def test_a_rewrite_reading_an_object_a_hint_builds_as_a_dict_fails() -> None:
    origin = Seed.of({"s": "0", "o": {"code": "0"}}, {"o": Builds(Order)})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake(reply='o["code"] == "1e-30"')

    Asking(fake, given, ABOUT, ("s", "o"), Kept()).tries(fake)

    assert failed(fake) == ["a rewrite may read o only as o.<field>"] * 4
    assert [request.holders for request in fake.requests] == [()] * 4
    assert fake.handed == []


# llm-rewrite-hint-built-object-each-built-object-counts
def test_self_of_no_known_class_is_shown_as_holding_an_object_in_the_ask_and_the_reason() -> None:
    origin = Seed.of({"self": {"code": "0"}, "s": "0"})
    given = GivenUp(CONDITION, PLAN, origin, MissWhy.TIMEOUT)
    fake = Fake(ran=ExecutionResult(frozenset(), (own(True),)))

    Asking(fake, given, ABOUT, ("s",), Kept("self")).tries(fake)

    assert dict(fake.requests[0].args)["self"] == "<holds an object>"
    assert fake.requests[0].holders == ()
    reason = (
        'the input {"self": <holds an object>, "s": "0"} already meets it, yet took the other side'
    )
    assert failed(fake)[0] == reason


class Loud:
    """An object whose ``__repr__`` raises, and whose contents no request may hold."""

    def __init__(self) -> None:
        self.secret = "hunter2"

    def __repr__(self) -> str:
        raise RuntimeError("repr ran")


def test_a_try_s_reason_writes_an_object_argument_without_running_its_code() -> None:
    given = GivenUp(CONDITION, PLAN, Seed.of({"s": "0", "o": Loud()}), MissWhy.TIMEOUT)
    fake = Fake(ran=ExecutionResult(frozenset(), (own(True),)))

    Asking(fake, given, ABOUT, ("s", "o"), Kept()).tries(fake)

    reason = 'the input {"s": "0", "o": <Loud object>} already meets it, yet took the other side'
    assert failed(fake) == [reason] * 4
    assert dict(fake.requests[0].args)["o"] == "<Loud object>"
