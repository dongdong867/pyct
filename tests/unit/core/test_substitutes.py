"""What substituted code calls: each router's answer, and the fork it records, on tracked values."""

import pytest

from pyct.core import substitutes
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.substitutes import PASSING, call, in_, is_, is_not, method, not_in


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

    assert in_(s, "ab\U00030000") is True
    assert not_in(s, "ab\U00030000") is False
    assert sink == [Downgrade(name="__contains__"), Downgrade(name="__contains__")]


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


def test_the_passing_frames_are_the_routers() -> None:
    # every operator's function runs the one code its factory makes
    names = {"is_", "is_not", "in_", "not_in", "call", "method", "route"}
    assert {code.co_name for code in PASSING} == names


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
    # an int element meets the float as `x == 2` does, a compare it follows
    assert in_(x, frozenset({2}), (2,)) is False
    assert expressions(sink)[-1] == (["==", "x", 2], False)
    # a bool beside a float is float's own answer, a downgrade named by the compare
    assert in_(x, frozenset({True}), (True,)) is False
    assert expressions(sink)[-1] == "__eq__"


def test_a_tracked_int_in_a_literal_display_of_floats_meets_each_as_python_does() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)

    assert in_(n, frozenset({1.5, 3.0}), (1.5, 3.0)) is True
    assert expressions(sink) == [(["==", "n", 1.5], False), (["==", "n", 3.0], True)]


def tracked_int(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt(value, expression="n", sink=sink)


def test_a_conversion_call_on_a_tracked_value_is_pyct_s() -> None:
    sink: list[SinkItem] = []
    n = tracked_int(3, sink)

    assert call(int, n) is n
    converted = call(float, n)
    assert (type(converted), converted.expression) == (ConcolicFloat, ["float", "n"])
    assert sink == []


def test_any_other_call_is_the_callee_s_own() -> None:
    sink: list[SinkItem] = []
    n = tracked_int(3, sink)
    calls: list[object] = []

    def own_int(*args: object, **kwargs: object) -> int:
        calls.append((args, kwargs))
        return 7

    assert call(own_int, n, base=2) == 7
    assert calls == [((n,), {"base": 2})]
    assert call(int, "12") == 12
    with pytest.raises(TypeError, match=r"int\(\) can't convert non-string with explicit base"):
        call(int, n, 10)
    assert sink == []


def test_a_plain_str_s_method_given_a_tracked_str_runs_on_a_tracked_str() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    found = method("abc".find, s)

    assert (type(found), repr(found), found.expression) == (
        ConcolicInt,
        "1",
        ["find", "'abc'", "s"],
    )
    starts = method("abc".startswith, s)
    assert starts.expression == ["startswith", "'abc'", "s"]
    assert sink == []


def test_a_plain_str_s_method_in_a_form_pyct_does_not_teach_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("x", expression="s", sink=sink)

    assert method("abcx".find, s, 1) == 3
    assert [item.name for item in sink if isinstance(item, Downgrade)] == ["find"]


def test_a_plain_str_past_what_cvc5_holds_is_python_s_answer_and_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    assert method("\U00030000b".find, s) == 1
    assert sink == [Downgrade(name="find")]


def test_a_plain_str_s_index_records_its_in_fork_before_it_raises() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("z", expression="s", sink=sink)

    with pytest.raises(ValueError, match="substring not found"):
        method("abc".index, s)

    assert expressions(sink) == [(["in", "s", "'abc'"], False)]


def test_any_other_method_call_is_the_bound_method_s_own() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    assert method(["a", s].index, s) == 1
    assert method("abc".find, "b") == 1
    assert method(str.find, "abc", s) == 1
    assert method("-".join, ["a", "b"]) == "a-b"
    # the list's own `index` compares s with each item, and `==` records that fork
    assert expressions(sink) == [(["==", "s", "'a'"], False)]


@pytest.mark.parametrize(
    ("operation", "left", "expression"),
    [
        (substitutes.add, 0.5, ["+", 0.5, "n"]),
        (substitutes.sub, 0.5, ["-", 0.5, "n"]),
        (substitutes.mul, 0.5, ["*", 0.5, "n"]),
        (substitutes.lt, 2.5, [">", "n", 2.5]),
        (substitutes.ge, 2.5, ["<=", "n", 2.5]),
        (substitutes.add, True, ["+", True, "n"]),
        (substitutes.eq, True, ["==", "n", True]),
    ],
)
def test_a_plain_float_or_bool_on_the_left_hands_the_operator_to_a_tracked_int(
    operation: object, left: object, expression: object
) -> None:
    sink: list[SinkItem] = []

    answer = operation(left, tracked_int(3, sink))  # pyrefly: ignore[not-callable]

    assert answer.expression == expression
    assert sink == []


def test_a_division_handed_over_records_its_zero_fork() -> None:
    sink: list[SinkItem] = []

    answer = substitutes.truediv(1.0, tracked_int(4, sink))

    assert (repr(answer), answer.expression) == ("0.25", ["/", 1.0, "n"])
    assert expressions(sink) == [(["!=", "n", 0], True)]


def test_a_plain_bool_on_the_left_of_a_tracked_bool_answers_with_both_conditions() -> None:
    sink: list[SinkItem] = []
    b = tracked_bool(False, sink)

    assert substitutes.bit_and(True, b).expression == ["&", True, [">", "x", 5]]
    assert substitutes.bit_or(False, b).expression == ["|", False, [">", "x", 5]]
    assert substitutes.bit_xor(True, b).expression == ["^", True, [">", "x", 5]]
    assert sink == []


def test_what_the_tracked_value_does_not_take_is_left_to_python() -> None:
    sink: list[SinkItem] = []
    n = tracked_int(2, sink)

    assert substitutes.power(0.5, n) == 0.25
    with pytest.raises(TypeError, match="unsupported operand"):
        substitutes.lshift(0.5, n)
    assert sink == []


def test_any_other_pair_is_python_s_own_operator() -> None:
    sink: list[SinkItem] = []
    f = ConcolicFloat(1.5, expression="f", sink=sink)

    assert substitutes.add(1, 2) == 3
    assert substitutes.add("a", "b") == "ab"
    assert substitutes.mul(0.5, 4) == 2.0
    # a plain float beside a tracked float or bool is the tracked value's own business
    assert substitutes.add(0.5, f).expression == ["+", 0.5, "f"]
    assert substitutes.add(0.5, tracked_bool(True, sink)) == 1.5
    with pytest.raises(TypeError, match="unsupported operand"):
        substitutes.sub("a", 1)
    assert substitutes.floordiv(7.0, tracked_int(2, sink)).expression == ["//", 7.0, "n"]
    assert substitutes.mod(7.0, tracked_int(2, sink)).expression == ["%", 7.0, "n"]
    # an operator a tracked int does not teach is its own answer and a downgrade, as ever
    assert substitutes.rshift(True, tracked_int(1, sink)) == 0
    assert Downgrade(name="__rrshift__") in sink
    assert substitutes.le(True, tracked_int(1, sink)).expression == [">=", "n", True]
    assert substitutes.gt(True, tracked_int(1, sink)).expression == ["<", "n", True]
    assert substitutes.ne(True, tracked_int(1, sink)).expression == ["!=", "n", True]
