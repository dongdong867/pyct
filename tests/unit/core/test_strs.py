from collections.abc import Callable

import pytest

from pyct.core import bools, strs, values
from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.strs import ConcolicStr

# the taught compares: the call, and the answer str's own gives for s = "abc"
TAUGHT_COMPARES: dict[str, tuple[Callable[[str], object], bool]] = {
    "<": (lambda s: s < "abc", False),
    "<=": (lambda s: s <= "abc", True),
    ">": (lambda s: s > "abc", False),
    ">=": (lambda s: s >= "abc", True),
    "==": (lambda s: s == "abc", True),
    "!=": (lambda s: s != "abc", False),
}


class Label(str):
    """A str of the target's own, the way an enum member or a library's name type is one."""


def test_a_concolic_str_is_a_real_str() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    assert isinstance(s, str)
    assert str.__eq__(s, "abc") is True
    assert s.expression == "s"


@pytest.mark.parametrize(("op", "case"), TAUGHT_COMPARES.items(), ids=list(TAUGHT_COMPARES))
def test_a_taught_compare_builds_its_expression_and_records_nothing(
    op: str, case: tuple[Callable[[str], object], bool]
) -> None:
    call, answer = case
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    result = call(s)

    assert isinstance(result, ConcolicBool)
    # the literal is written as repr writes it, quotes and all, so it reads apart from a name
    assert result.expression == [op, "s", "'abc'"]
    # int.__bool__, not bool(result): bool() would record the fork this test is not about
    assert int.__bool__(result) is answer
    assert sink == []


def test_a_literal_holding_a_single_quote_is_written_in_double_quotes() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    result = s == "it's"

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["==", "s", '"it\'s"']


def test_a_compare_with_another_concolic_str_takes_its_expression() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)
    t = ConcolicStr("abd", expression="t", sink=sink)

    result = s != t

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["!=", "s", "t"]


def test_a_literal_on_the_left_is_the_compare_python_runs() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    # Python gives a subclass's reflected method the first turn, so `"abc" == s` runs on s
    result = "abc" == s  # noqa: SIM300 - the order this test is about

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["==", "s", "'abc'"]


def test_a_literal_on_the_left_of_an_order_is_the_reflected_compare() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    # Python swaps the operands itself, so `"b" < s` runs `s > "b"`; nothing here reflects
    result = "b" < s  # noqa: SIM300 - the order this test is about

    assert isinstance(result, ConcolicBool)
    assert result.expression == [">", "s", "'b'"]
    assert int.__bool__(result) is False


def test_less_than_a_non_str_is_left_to_python_to_refuse() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    # both sides answer NotImplemented, so Python raises the TypeError the target wrote
    with pytest.raises(TypeError, match="'<' not supported"):
        s < 5  # pyrefly: ignore[unsupported-operation]  # noqa: B015 - the raise is the point
    assert sink == []


def test_a_str_of_the_targets_own_is_a_literal_of_its_plain_value() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    result = s == Label("abc")

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["==", "s", "'abc'"]


def test_equal_to_a_non_str_is_pythons_own_answer() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("5", expression="s", sink=sink)

    # both sides answer NotImplemented; Python settles `==` by identity instead of raising
    assert (s == 5) is False
    assert (s != 5) is True
    assert (s == None) is False  # noqa: E711 - the target's spelling
    assert sink == []


def test_a_concolic_str_hashes_as_its_value() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    # a class body that defines __eq__ loses __hash__ unless it keeps str's
    assert hash(s) == hash("abc")


def test_every_operation_that_reaches_strs_own_goes_through_the_helper() -> None:
    # a call into str written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicStr's dunders are written in three files: its own, bools for the compare closures
    # and values for the downgrade closures, so the scan covers all three. A compare in strs
    # hands the call to a closure it holds, so what a function holds counts as what it calls
    written_here = {
        name: member
        for name, member in vars(ConcolicStr).items()
        if name.startswith("__")
        and (code := getattr(member, "__code__", None)) is not None
        and code.co_filename in {strs.__file__, bools.__file__, values.__file__}
    }

    without_the_helper = {
        name for name, member in written_here.items() if not _reaches_through_the_helper(member)
    }

    # the scan read the taught compares, so an empty answer is not an empty scan
    assert {"__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__"} <= written_here.keys()
    assert without_the_helper == set()


def _reaches_through_the_helper(function: object) -> bool:
    """Whether a function calls `own`, or holds a function that does, the way a closure does."""
    code = getattr(function, "__code__", None)
    if code is None:
        return False
    if "own" in code.co_names:
        return True
    held = [cell.cell_contents for cell in getattr(function, "__closure__", None) or ()]
    return any(_reaches_through_the_helper(inner) for inner in held)
