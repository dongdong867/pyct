"""The searches a ConcolicStr teaches: what each answers, the expression it carries, and the
forms it leaves to str as a downgrade."""

from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

# each taught search on s = "abcb": the call, the expression it carries, and str's own answer
TAUGHT_SEARCHES: dict[str, tuple[Callable[[str], object], list[object], object]] = {
    "s.find('b')": (lambda s: s.find("b"), ["find", "s", "'b'"], 1),
}


class Label(str):
    """A str of the target's own, the way an enum member or a library's name type is one."""


def _tracked(value: str = "abcb", sink: list[SinkItem] | None = None) -> ConcolicStr:
    return ConcolicStr(value, expression="s", sink=[] if sink is None else sink)


@pytest.mark.parametrize(
    ("call", "expression", "answer"), TAUGHT_SEARCHES.values(), ids=list(TAUGHT_SEARCHES)
)
def test_a_taught_search_answers_as_str_does_and_carries_its_expression(
    call: Callable[[str], object], expression: list[object], answer: object
) -> None:
    sink: list[SinkItem] = []

    result = call(_tracked(sink=sink))

    # a bool answer is a ConcolicBool and a position or a count a ConcolicInt, so a compare
    # on it later is a fork on s
    assert isinstance(result, ConcolicBool if isinstance(answer, bool) else ConcolicInt)
    assert result.expression == expression
    # int.__eq__, not ==: a tracked answer's == builds a compare rather than answering
    assert int.__eq__(result, answer)
    assert sink == []


def test_a_tracked_substring_is_written_by_its_expression() -> None:
    sink: list[SinkItem] = []
    s = _tracked(sink=sink)
    t = ConcolicStr("c", expression="t", sink=sink)

    result = s.find(t)

    assert isinstance(result, ConcolicInt)
    assert result.expression == ["find", "s", "t"]
    assert int.__index__(result) == 2


def test_a_substring_of_the_targets_own_str_type_is_a_literal_of_its_plain_value() -> None:
    result = _tracked().find(Label("c"))

    assert isinstance(result, ConcolicInt)
    assert result.expression == ["find", "s", "'c'"]


def test_an_empty_substring_is_followed_as_python_answers_it() -> None:
    result = _tracked().find("")

    assert isinstance(result, ConcolicInt)
    assert result.expression == ["find", "s", "''"]
    assert int.__index__(result) == 0


def test_a_search_answer_compared_with_a_tracked_int_is_one_expression() -> None:
    sink: list[SinkItem] = []
    n = ConcolicInt(1, expression="n", sink=sink)

    result = _tracked(sink=sink).find("x") < n

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["<", ["find", "s", "'x'"], "n"]


def test_in_answers_as_str_does_in_pythons_operand_order() -> None:
    sink: list[SinkItem] = []

    result = _tracked(sink=sink).__contains__("b")

    # the needle comes first, the way the target wrote `"b" in s`
    assert isinstance(result, ConcolicBool)
    assert result.expression == ["in", "'b'", "s"]
    assert int.__bool__(result) is True
    assert sink == []


def test_in_on_a_tracked_needle_is_written_by_its_expression() -> None:
    sink: list[SinkItem] = []
    t = ConcolicStr("cb", expression="t", sink=sink)

    result = _tracked(sink=sink).__contains__(t)

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["in", "t", "s"]


# a probe whose text is fixed here, so the line and column of each fork are exact
PROBE = "def probe(v):\n    y = 'b' in v\n    z = 'x' not in v\n    return y, z\n"


def _probe() -> Callable[[object], object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def test_in_records_its_fork_where_it_runs_and_not_in_reverses_the_side() -> None:
    sink: list[SinkItem] = []

    answer = _probe()(_tracked(sink=sink))

    # CPython tests the answer of `in` for truth on the spot, so each fork is on its own
    # assignment, at the column the `in` starts; `not in` records `in` with its own answer
    assert answer == (True, True)
    assert sink == [
        Branch(expression=["in", "'b'", "s"], taken=True, site=Site(file="<probe>", line=2, col=8)),
        Branch(
            expression=["in", "'x'", "s"], taken=False, site=Site(file="<probe>", line=3, col=8)
        ),
    ]


# a probe for the searches that raise when the substring is missing, one per line
RAISING_PROBE = "def probe(v, sub):\n    return v.index(sub)\n"


def _raising_probe() -> Callable[[object, object], object]:
    namespace: dict[str, object] = {}
    exec(compile(RAISING_PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def test_index_records_the_in_fork_at_the_call_before_its_answer() -> None:
    sink: list[SinkItem] = []

    result = _raising_probe()(_tracked(sink=sink), "b")

    # the fork says the substring is there, in Python's operand order, at the call's column
    assert isinstance(result, ConcolicInt)
    assert result.expression == ["index", "s", "'b'"]
    assert int.__index__(result) == 1
    assert sink == [
        Branch(expression=["in", "'b'", "s"], taken=True, site=Site(file="<probe>", line=2, col=11))
    ]


def test_index_of_a_missing_substring_raises_as_the_targets_after_its_fork() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(ValueError, match="substring not found") as raised:
        _raising_probe()(_tracked(sink=sink), "x")

    # the fork went in first, so the raising input's line lists it, taken false
    assert raised_by_target(raised.value)
    assert sink == [
        Branch(
            expression=["in", "'x'", "s"], taken=False, site=Site(file="<probe>", line=2, col=11)
        )
    ]


# a taught search in a form pyct does not encode: the call, and the name its downgrade carries
FORMS_NOT_ENCODED: dict[str, tuple[Callable[[str], object], str]] = {
    "past the last character in s": (lambda s: "\U00030000" in s, "__contains__"),
    "s.find('b', 2)": (lambda s: s.find("b", 2), "find"),
    "s.find('b', 0, 2)": (lambda s: s.find("b", 0, 2), "find"),
    "s.find(past the last character)": (lambda s: s.find("\U00030000"), "find"),
    "s.index('b', 2)": (lambda s: s.index("b", 2), "index"),
}


@pytest.mark.parametrize(("call", "name"), FORMS_NOT_ENCODED.values(), ids=list(FORMS_NOT_ENCODED))
def test_a_form_pyct_does_not_encode_is_strs_own_and_a_downgrade(
    call: Callable[[str], object], name: str
) -> None:
    sink: list[SinkItem] = []

    result = call(_tracked(sink=sink))

    # str's own answer, plain, and the line names the method
    assert result == call("abcb")
    assert not isinstance(result, ConcolicBool | ConcolicInt)
    assert sink == [Downgrade(name=name)]


# a taught search given what str refuses: the call, and the error str raises for it
REFUSED: dict[str, tuple[Callable[[str], object], type[Exception]]] = {
    "s.find(5)": (lambda s: s.find(5), TypeError),  # pyrefly: ignore[bad-argument-type]
    "5 in s": (lambda s: 5 in s, TypeError),  # pyrefly: ignore[unsupported-operation]
    # a form pyct does not encode raises out of str's own call, with no fork before it
    "s.index('x', 2)": (lambda s: s.index("x", 2), ValueError),
}


@pytest.mark.parametrize(("call", "error"), REFUSED.values(), ids=list(REFUSED))
def test_what_str_refuses_raises_as_the_targets_and_records_nothing(
    call: Callable[[str], object], error: type[Exception]
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(error) as raised:
        call(_tracked(sink=sink))

    assert raised_by_target(raised.value)
    assert sink == []


def test_a_keyword_is_refused_the_way_str_refuses_it_and_records_nothing() -> None:
    sink: list[SinkItem] = []

    # str's searches take no keywords, so the call raises before anything runs
    with pytest.raises(TypeError, match="keyword"):
        _tracked(sink=sink).find("b", start=2)  # pyrefly: ignore[unexpected-keyword]

    with pytest.raises(TypeError, match="keyword"):
        "abcb".find("b", start=2)  # pyrefly: ignore[unexpected-keyword]
    assert sink == []
