import subprocess
import sys
import textwrap

import pytest

from pyct.core import values
from pyct.core.branch import BranchSink, Downgrade, SinkItem
from pyct.core.values import raised_by_target


class StandIn:
    """A base type standing in for int, so the derivation is read away from int's methods."""

    def untaught(self) -> str:
        return "the base type's"

    def taught(self) -> str:
        return "the base type's"

    def plumbing(self) -> str:
        return "the base type's"

    def raises(self) -> str:
        raise ValueError("the target's own")

    def undecided(self) -> object:
        return NotImplemented

    @classmethod
    def from_text(cls, text: str) -> str:
        return text

    @staticmethod
    def helper() -> str:
        return "the base type's"

    @property
    def width(self) -> int:
        return 1


# what the concolic types below keep as the base type's, plus one name the stand-in does not
# define: a kept name is a promise about what is not wrapped, not a promise that it exists
KEPT = ("plumbing", "dropped")

# the stand-in inherits __str__ from object, so reading what it defines never reaches it
INHERITED = ("__str__",)


class Untaught(StandIn):
    """A concolic type that teaches nothing: every method the stand-in defines is a downgrade."""

    sink: BranchSink

    def __init__(self, sink: BranchSink) -> None:
        self.sink = sink


class Taught(StandIn):
    """The same type, with one name written in its class body."""

    sink: BranchSink

    def __init__(self, sink: BranchSink) -> None:
        self.sink = sink

    def taught(self) -> str:
        return "the concolic type's"


# the names each body held before the derivation ran, so a test can show that a downgrade is
# installed under a name the concolic type never wrote
UNTAUGHT_BODY = frozenset(vars(Untaught))

values.downgrade_the_rest(Untaught, StandIn, kept=KEPT, inherited=INHERITED)
values.downgrade_the_rest(Taught, StandIn, kept=KEPT, inherited=INHERITED)


def test_a_method_neither_set_names_becomes_a_downgrade() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    assert value.untaught() == "the base type's"

    assert sink == [Downgrade(name="untaught")]
    # the class body never wrote the name; the derivation is what put a wrapper under it
    assert "untaught" not in UNTAUGHT_BODY
    assert "untaught" in vars(Untaught)


def test_teaching_a_method_is_adding_its_name_to_the_class_body() -> None:
    untaught_sink: list[SinkItem] = []
    taught_sink: list[SinkItem] = []

    assert Untaught(untaught_sink).taught() == "the base type's"
    assert Taught(taught_sink).taught() == "the concolic type's"

    # the two types differ in one line, and that line is the whole difference
    assert untaught_sink == [Downgrade(name="taught")]
    assert taught_sink == []


def test_a_kept_method_stays_the_base_types_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    assert value.plumbing() == "the base type's"

    assert sink == []
    assert "plumbing" not in vars(Untaught)


def test_a_kept_name_the_base_type_does_not_define_installs_nothing() -> None:
    # the derivation ran at import and did not raise over it
    assert "dropped" not in vars(Untaught)
    assert not hasattr(Untaught, "dropped")


def test_a_classmethod_a_staticmethod_and_a_property_are_not_wrapped() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    # no tracked value reaches any of the three as a receiver, so none can lose a condition
    assert Untaught.from_text("text") == "text"
    assert Untaught.helper() == "the base type's"
    assert value.width == 1

    assert {"from_text", "helper", "width"} & set(vars(Untaught)) == set()
    assert sink == []


def test_a_name_the_base_type_inherits_is_wrapped_when_it_is_named() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    # object's __str__ answers by asking __repr__, which is neither named nor wrapped
    assert str(value) == repr(value)

    assert sink == [Downgrade(name="__str__")]


def test_a_raise_out_of_the_base_types_method_is_the_targets() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    with pytest.raises(ValueError) as raised:
        value.raises()

    assert raised_by_target(raised.value)
    # the call never answered, so nothing was lost
    assert sink == []


def test_a_method_that_answers_not_implemented_records_nothing() -> None:
    sink: list[SinkItem] = []
    value = Untaught(sink)

    # the other operand's reflected method gets its turn; only a real result is a lost condition
    assert value.undecided() is NotImplemented

    assert sink == []


def test_a_stand_in_derives_through_the_shared_module_alone() -> None:
    # this session has already imported every core module, so only a fresh interpreter shows
    # what the shared module needs on its own. None in sys.modules makes importing that name
    # raise, so a shared module that reached into ints or bools would fail here
    script = textwrap.dedent(
        """
        import sys

        sys.modules["pyct.core.ints"] = None
        sys.modules["pyct.core.bools"] = None

        from pyct.core.values import downgrade_the_rest


        class StandIn:
            def untaught(self):
                return "the base type's"


        class Untaught(StandIn):
            def __init__(self, sink):
                self.sink = sink


        downgrade_the_rest(Untaught, StandIn, kept=(), inherited=())
        sink = []
        print(Untaught(sink).untaught(), sink)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "the base type's [Downgrade(name='untaught')]\n"
