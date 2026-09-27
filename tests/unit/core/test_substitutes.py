"""What substituted code calls: each router's answer, and the fork it records, on tracked values."""

import pytest

from pyct.core import bound
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


@pytest.mark.parametrize(("left", "right"), [(True, True), (True, False), (False, False)])
def test_two_tracked_bools_are_identical_when_they_are_equal(left: bool, right: bool) -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool(left, expression="flag", sink=sink)
    other = ConcolicBool(right, expression="other", sink=sink)

    # a bool is one of two singletons, so two bools are the same object when they are equal
    assert is_(flag, other) is (left is right)
    assert is_not(flag, other) is (left is not right)
    assert expressions(sink) == [(["==", "flag", "other"], left is right)] * 2


def test_a_plain_bool_held_by_a_name_meets_a_tracked_bool_as_the_constant_does() -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool(True, expression="flag", sink=sink)
    held = True

    assert is_(held, flag) is True
    assert is_(flag, 1) is False
    assert expressions(sink) == [("flag", True)]


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
    # a bool beside a float is the double 1.0 or 0.0, a compare it follows too
    assert in_(x, frozenset({True}), (True,)) is False
    assert expressions(sink)[-1] == (["==", "x", True], False)


def test_a_tracked_int_in_a_literal_display_of_floats_meets_each_as_python_does() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(3, expression="n", sink=sink)

    assert in_(n, frozenset({1.5, 3.0}), (1.5, 3.0)) is True
    assert expressions(sink) == [(["==", "n", 1.5], False), (["==", "n", 3.0], True)]


def tracked_int(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt(value, expression="n", sink=sink)


@pytest.mark.parametrize(
    ("builtin", "router"),
    [(int, bound.int_), (float, bound.float_), (bool, bound.bool_), (map, bound.map_)],
)
def test_python_s_own_conversion_is_handed_pyct_s_router(builtin: object, router: object) -> None:
    assert call(builtin) is router


def test_any_other_callee_is_handed_back_to_be_called_as_written() -> None:
    def own_int(value: object) -> int:
        return 7

    for callee in (own_int, str, len, [1], None):
        assert call(callee) is callee


def test_a_conversion_router_on_a_tracked_value_is_pyct_s() -> None:
    sink: list[SinkItem] = []
    n = tracked_int(3, sink)

    assert call(int)(n) is n
    converted = call(float)(n)
    assert (type(converted), converted.expression) == (ConcolicFloat, ["float", "n"])
    assert sink == []


def test_a_conversion_router_on_anything_else_is_python_s_own() -> None:
    sink: list[SinkItem] = []
    n = tracked_int(3, sink)

    assert call(int)("12") == 12
    assert call(float)(" 1.5 ") == 1.5
    assert call(bool)([]) is False
    with pytest.raises(TypeError, match=r"int\(\) can't convert non-string with explicit base"):
        call(int)(n, 10)
    assert sink == []


def test_a_str_literal_s_method_given_a_tracked_str_runs_on_a_tracked_str() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    found = method("abc".find, s)

    assert (type(found), repr(found), found.expression) == (
        ConcolicInt,
        "1",
        ["find", "'abc'", "s"],
    )
    assert method("abc".startswith, s).expression == ["startswith", "'abc'", "s"]
    assert sink == []


def test_a_str_literal_s_method_in_a_form_pyct_does_not_teach_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("a", expression="s", sink=sink)

    assert method("abab".replace, s, "x", 2) == "xbxb"
    assert sink == [Downgrade(name="replace")]


def test_a_keyword_call_is_the_method_s_own_and_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr(",", expression="s", sink=sink)

    assert method("a,b".split, sep=s) == ["a", "b"]
    assert sink == [Downgrade(name="split")]


def test_a_keyword_call_the_method_refuses_raises_in_python_s_own_words() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr(",", expression="s", sink=sink)

    with pytest.raises(TypeError) as written:
        "a,b".count(sub=",")  # pyrefly: ignore[unexpected-keyword]
    with pytest.raises(TypeError) as raised:
        method("a,b".count, sub=s)

    assert str(raised.value) == str(written.value)
    assert sink == []


def test_a_literal_past_what_cvc5_holds_is_python_s_answer_and_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    assert method("\U00030000b".find, s) == 1
    assert sink == [Downgrade(name="find")]


def test_a_str_literal_s_index_records_its_in_fork_before_it_raises() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("z", expression="s", sink=sink)

    with pytest.raises(ValueError, match="substring not found"):
        method("abc".index, s)

    assert expressions(sink) == [(["in", "s", "'abc'"], False)]


def test_any_other_method_call_is_the_method_s_own() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("b", expression="s", sink=sink)

    assert method("abc".find, "b") == 1
    assert method(str.find, "abc", s) == 1
    assert method("-".join, ["a", "b"]) == "a-b"
    assert method(["a", "b"].index, "b") == 1
    assert sink == []


def test_the_passing_frames_are_the_routers() -> None:
    assert {code.co_name for code in PASSING} == {
        "is_",
        "is_not",
        "in_",
        "not_in",
        "call",
        "method",
        "_on_text",
        "handed",
        "answer",
        "len",
        "ord",
        "chr",
        "_routed",
        "int_",
        "float_",
        "bool_",
        "map_",
        "type_",
        "itself",
        # each `math` function's router
        "route",
        # a chained compare's link: `Searched`'s and `Identity`'s `in`, and the compares a
        # link hands on to the next
        "__contains__",
        "forward",
    }
    assert {
        code.co_qualname for code in PASSING if code.co_name in ("__contains__", "forward")
    } == {"Searched.__contains__", "Identity.__contains__", "_forwarded.<locals>.forward"}
