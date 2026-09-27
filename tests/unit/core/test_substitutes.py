"""What substituted code calls: each router's answer, and the fork it records, on tracked values."""

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.substitutes import PASSING, in_, is_, is_not, not_in


def expressions(sink: list[SinkItem]) -> list[object]:
    """What the sink holds, each fork as its expression and side, each downgrade by name."""
    return [
        (item.expression, item.taken) if isinstance(item, Branch) else item.name for item in sink
    ]


def tracked_bool(value: bool, sink: list[SinkItem]) -> ConcolicBool:
    """A compare's answer, `x > 5`, standing for the given bool."""
    return ConcolicBool(value, expression=[">", "x", 5], sink=sink)


@pytest.mark.parametrize(
    ("value", "call", "answer"),
    [
        (True, lambda b: is_(b, True), True),
        (False, lambda b: is_(b, True), False),
        (False, lambda b: is_(b, False), True),
        (True, lambda b: is_(True, b), True),
        (False, lambda b: is_(False, b), True),
        (True, lambda b: is_not(b, True), False),
        (False, lambda b: is_not(b, True), True),
        (True, lambda b: is_not(False, b), True),
    ],
)
def test_a_tracked_bool_against_true_or_false_answers_as_the_bool_it_stands_for(
    value: bool, call: object, answer: bool
) -> None:
    sink: list[SinkItem] = []

    result = call(tracked_bool(value, sink))  # pyrefly: ignore[not-callable]

    assert result is answer
    # its fork is recorded where the `is` runs, as `if b:` records it
    assert expressions(sink) == [([">", "x", 5], value)]


def test_identity_with_any_other_operand_is_pythons_own_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    b = tracked_bool(True, sink)
    x = ConcolicInt(1, expression="x", sink=sink)

    assert is_(b, None) is False
    assert is_(b, b) is True
    assert is_(x, True) is False
    assert is_not(True, True) is False
    assert is_(1, True) is False
    assert sink == []


def test_in_on_a_tracked_string_hands_back_its_condition_untested() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("xab", expression="s", sink=sink)

    found = in_("a", s)
    missing = not_in("b", s)

    assert isinstance(found, ConcolicBool) and isinstance(missing, ConcolicBool)
    assert (found.expression, int.__bool__(found)) == (["in", "'a'", "s"], True)
    assert (missing.expression, int.__bool__(missing)) == (["not in", "'b'", "s"], False)
    # nothing is tested until the target tests the answer
    assert sink == []
    assert bool(missing) is False
    assert expressions(sink) == [(["not in", "'b'", "s"], False)]


def test_in_on_a_tracked_string_in_a_form_pyct_does_not_encode_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("xab", expression="s", sink=sink)

    assert in_("\U00030000", s) is False
    assert not_in("\U00030000", s) is True
    assert expressions(sink) == ["__contains__", "__contains__"]
    with pytest.raises(TypeError):
        not_in(1, s)


def test_a_tracked_string_in_a_plain_one_carries_the_plain_one_as_a_literal() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    found = in_(s, "abc")
    missing = not_in(s, "abc")

    assert isinstance(found, ConcolicBool) and isinstance(missing, ConcolicBool)
    assert (found.expression, int.__bool__(found)) == (["in", "s", "'abc'"], True)
    assert (missing.expression, int.__bool__(missing)) == (["not in", "s", "'abc'"], False)
    assert sink == []


def test_a_tracked_string_in_a_plain_one_the_solver_cannot_hold_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)
    # substituted code as the target's module holds it: each router called where the `in` was
    namespace: dict[str, object] = {"in_": in_, "not_in": not_in}
    source = 'def look(s):\n    return in_(s, "ab\\U00030000"), not_in(s, "ab\\U00030000")\n'
    exec(compile(source, "<looked>", "exec"), namespace)
    look = namespace["look"]
    assert callable(look)

    assert look(s) == (True, False)
    # each downgrade names the target's call, not the router it went through
    assert sink == [
        Downgrade(name="__contains__", site=Site(file="<looked>", line=2, col=11)),
        Downgrade(name="__contains__", site=Site(file="<looked>", line=2, col=35)),
    ]


def test_a_tracked_value_in_a_literal_display_is_searched_for_in_the_order_written() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(5, expression="x", sink=sink)

    assert in_(x, frozenset({1, 5, 9}), (1, 5, 9)) is True
    assert not_in(x, frozenset({1, 5, 9}), (1, 5, 9)) is False
    # one `==` fork per element tried, until one holds, for `in` and `not in` alike
    tried = [(["==", "x", 1], False), (["==", "x", 5], True)]
    assert expressions(sink) == tried + tried


def test_a_plain_value_in_a_literal_display_is_pythons_own_lookup() -> None:
    log: list[object] = []

    class Key(str):
        def __eq__(self, other: object) -> bool:
            log.append(other)
            return str.__eq__(self, other)

        __hash__ = str.__hash__

    # the set answers by hash, as written; the elements are never compared one by one
    assert in_(Key("z"), frozenset({"x", "y"}), ("x", "y")) is False
    assert log == []


def test_an_unhashable_value_in_a_literal_display_raises_as_python_does() -> None:
    with pytest.raises(TypeError, match="unhashable"):
        in_([1], frozenset({1, 2}), (1, 2))


def test_the_passing_frames_are_the_four_routers() -> None:
    assert {code.co_name for code in PASSING} == {"is_", "is_not", "in_", "not_in"}


def test_a_tracked_bool_searched_in_a_literal_display_of_bools_records_its_fork() -> None:
    sink: list[SinkItem] = []
    b = tracked_bool(False, sink)

    # the tracked value is on the left of each `==`, so it answers, as `b == True` does
    assert in_(b, frozenset({True}), (True,)) is False
    assert not_in(b, frozenset({True}), (True,)) is True
    assert expressions(sink) == [(["==", [">", "x", 5], True], False)] * 2


def test_a_tracked_value_in_a_literal_display_tries_each_element_in_order_until_one_holds() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(1, expression="x", sink=sink)

    # True and 1 are equal, as Python has them; the search stops at the first that holds
    assert in_(x, frozenset({True, 2}), (True, 2)) is True
    assert expressions(sink) == [(["==", "x", True], True)]


def test_a_tracked_float_in_a_literal_display_is_searched_for_in_the_order_written() -> None:
    sink: list[SinkItem] = []
    x = ConcolicFloat(1.5, expression="x", sink=sink)

    assert in_(x, frozenset({2.5, 1.5}), (2.5, 1.5)) is True
    assert expressions(sink) == [(["==", "x", 2.5], False), (["==", "x", 1.5], True)]
    # an int element meets the float as `x == 2` does, a compare floats do not teach yet
    assert in_(x, frozenset({2}), (2,)) is False
    assert expressions(sink)[-1] == "__eq__"
