"""The pieces a ConcolicStr teaches: the tracked str each hands back, the fork an index records
before it may raise, and the forms left to str as a downgrade."""

import operator
import sys
from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

# a character past the last one cvc5 holds
PAST_CVC5 = "\U00030000"


class Label(str):
    """A str of the target's own, the way an enum member or a library's name type is one."""


class Escaped(str):
    """A str of a library's own that decides what a str joined on its left gives, the way
    markupsafe's Markup escapes that str."""

    def __radd__(self, other: object) -> object:
        # str's own copy of the other side: str(other) would record a downgrade of its own
        return ("joined by Escaped", str.__str__(other) if isinstance(other, str) else other)


class Declining(str):
    """A str of a library's own whose `__radd__` declines a str, the way numpy.str_'s does,
    so str's own concatenation answers."""

    def __radd__(self, other: object) -> object:
        return NotImplemented


class Column:
    """A value of a library's own that decides what a str joined on its left gives."""

    def __radd__(self, other: object) -> object:
        return ("joined by Column", str.__str__(other) if isinstance(other, str) else other)


class Position:
    """An object Python indexes with through its ``__index__``."""

    def __index__(self) -> int:
        return 1


def _tracked(value: str = "abcb", sink: list[SinkItem] | None = None) -> ConcolicStr:
    return ConcolicStr(value, expression="s", sink=[] if sink is None else sink)


# each piece of s = "abcb" that records no fork: the call, and the expression it carries
PIECES: dict[str, tuple[Callable[[str], object], Expression]] = {
    "s[1:3]": (lambda s: s[1:3], ["[:]", "s", 1, 3]),
    "s[2:]": (lambda s: s[2:], ["[:]", "s", 2, None]),
    "s[:-1]": (lambda s: s[:-1], ["[:]", "s", None, -1]),
    "s[:]": (lambda s: s[:], ["[:]", "s", None, None]),
    # a slice clamps to the string, so a bound past either end is followed as it is
    "s[-9:9]": (lambda s: s[-9:9], ["[:]", "s", -9, 9]),
    # a plain bool is the int it stands for
    "s[True:]": (lambda s: s[True:], ["[:]", "s", 1, None]),
    "s + 'x'": (lambda s: s + "x", ["+", "s", "'x'"]),
    "'x' + s": (lambda s: "x" + s, ["+", "'x'", "s"]),
    "Label('x') + s": (lambda s: Label("x") + s, ["+", "'x'", "s"]),
    "s + Label('x')": (lambda s: s + Label("x"), ["+", "s", "'x'"]),
    "s + ''": (lambda s: s + "", ["+", "s", "''"]),
    "s.replace('b', 'x')": (lambda s: s.replace("b", "x"), ["replace", "s", "'b'", "'x'"]),
    "s.replace('b', '')": (lambda s: s.replace("b", ""), ["replace", "s", "'b'", "''"]),
    "s.removeprefix('ab')": (lambda s: s.removeprefix("ab"), ["removeprefix", "s", "'ab'"]),
    "s.removeprefix('')": (lambda s: s.removeprefix(""), ["removeprefix", "s", "''"]),
    "s.removesuffix('cb')": (lambda s: s.removesuffix("cb"), ["removesuffix", "s", "'cb'"]),
    "s.removesuffix('x')": (lambda s: s.removesuffix("x"), ["removesuffix", "s", "'x'"]),
}


@pytest.mark.parametrize(("call", "expression"), PIECES.values(), ids=list(PIECES))
def test_a_piece_is_a_tracked_str_carrying_its_expression(
    call: Callable[[str], object], expression: Expression
) -> None:
    sink: list[SinkItem] = []

    result = call(_tracked(sink=sink))

    assert isinstance(result, ConcolicStr)
    assert result.expression == expression
    # str.__eq__, not ==: a tracked str's == builds a compare rather than answering
    assert str.__eq__(result, call("abcb")) is True
    assert sink == []


def test_a_tracked_str_on_either_side_is_written_by_its_expression() -> None:
    sink: list[SinkItem] = []
    s = _tracked(sink=sink)
    t = ConcolicStr("xb", expression="t", sink=sink)

    assert _expression_of(s + t) == ["+", "s", "t"]
    assert _expression_of(s.replace("b", t)) == ["replace", "s", "'b'", "t"]
    assert _expression_of(s.removeprefix(t)) == ["removeprefix", "s", "t"]
    assert _expression_of(s.removesuffix(t)) == ["removesuffix", "s", "t"]


def test_a_piece_of_a_piece_nests_its_expression() -> None:
    sink: list[SinkItem] = []

    piece = _tracked(sink=sink)[1:]
    assert isinstance(piece, ConcolicStr)

    result = piece[0]

    assert _expression_of(result) == ["[]", ["[:]", "s", 1, None], 0]
    # the index measures the piece it indexes
    assert [item.expression for item in sink if isinstance(item, Branch)] == [
        [">", ["len", ["[:]", "s", 1, None]], 0]
    ]


def _expression_of(result: object) -> Expression:
    assert isinstance(result, ConcolicStr), result
    return result.expression


# a probe whose text is fixed here, so the line and column of each fork are exact
PROBE = "def probe(v, i):\n    return v[i]\n"


def _probe() -> Callable[[object, object], object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


# an index into s = "abcb": the index, the long-enough fork it records, and the side taken.
# A negative index counts from the end, so s[-1] needs one character and s[-4] needs four
INDEXES: dict[str, tuple[int, Expression, bool]] = {
    "s[0]": (0, [">", ["len", "s"], 0], True),
    "s[3]": (3, [">", ["len", "s"], 3], True),
    "s[-1]": (-1, [">=", ["len", "s"], 1], True),
    "s[-4]": (-4, [">=", ["len", "s"], 4], True),
    "s[True]": (True, [">", ["len", "s"], 1], True),
}


@pytest.mark.parametrize(("index", "fork", "taken"), INDEXES.values(), ids=list(INDEXES))
def test_an_index_records_whether_s_is_long_enough_before_it_indexes(
    index: int, fork: Expression, taken: bool
) -> None:
    sink: list[SinkItem] = []

    result = _probe()(_tracked(sink=sink), index)

    assert sink == [Branch(expression=fork, taken=taken, site=Site("<probe>", 2, 11))]
    assert isinstance(result, ConcolicStr)
    assert result.expression == ["[]", "s", int(index)]
    assert str.__eq__(result, "abcb"[index]) is True


@pytest.mark.parametrize(
    ("index", "fork"),
    [(4, [">", ["len", "s"], 4]), (-5, [">=", ["len", "s"], 5])],
    ids=["s[4]", "s[-5]"],
)
def test_an_index_past_the_end_records_its_fork_not_taken_and_raises_as_the_targets(
    index: int, fork: Expression
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(IndexError) as raised:
        _probe()(_tracked(sink=sink), index)

    # the fork went in before str's own index raised, so the raising input's line lists it
    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=fork, taken=False, site=Site("<probe>", 2, 11))]


def test_the_empty_string_has_no_index_at_all() -> None:
    sink: list[SinkItem] = []

    with pytest.raises(IndexError):
        _tracked("", sink=sink)[0]

    assert [(item.expression, item.taken) for item in sink if isinstance(item, Branch)] == [
        ([">", ["len", "s"], 0], False)
    ]


def _tracked_int(sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt(1, expression="n", sink=sink)


# a piece in a form pyct does not encode: the call on s = "abcb" and a tracked int n = 1 in the
# same sink, and the name its downgrade carries
FORMS_NOT_ENCODED: dict[str, tuple[Callable[[str, int], object], str]] = {
    "s[n]": (lambda s, n: s[n], "__getitem__"),
    "s[n:]": (lambda s, n: s[n:], "__getitem__"),
    "s[:n]": (lambda s, n: s[:n], "__getitem__"),
    "s[::-1]": (lambda s, n: s[::-1], "__getitem__"),
    "s[0:3:1]": (lambda s, n: s[0:3:1], "__getitem__"),
    "s[Position()]": (lambda s, n: s[Position()], "__getitem__"),  # pyrefly: ignore[bad-index]
    "s[n == 1]": (lambda s, n: s[n == 1], "__getitem__"),
    "s.replace('b', 'x', 1)": (lambda s, n: s.replace("b", "x", 1), "replace"),
    "s.replace('', 'x')": (lambda s, n: s.replace("", "x"), "replace"),
    "s.replace(past cvc5, 'x')": (lambda s, n: s.replace(PAST_CVC5, "x"), "replace"),
    "s.replace('b', past cvc5)": (lambda s, n: s.replace("b", PAST_CVC5), "replace"),
    "s.removeprefix(past cvc5)": (lambda s, n: s.removeprefix(PAST_CVC5), "removeprefix"),
    "s.removesuffix(past cvc5)": (lambda s, n: s.removesuffix(PAST_CVC5), "removesuffix"),
    "s + past cvc5": (lambda s, n: s + PAST_CVC5, "__add__"),
    "past cvc5 + s": (lambda s, n: PAST_CVC5 + s, "__radd__"),
}


@pytest.mark.parametrize(("call", "name"), FORMS_NOT_ENCODED.values(), ids=list(FORMS_NOT_ENCODED))
def test_a_form_pyct_does_not_encode_is_strs_own_and_a_downgrade(
    call: Callable[[str, int], object], name: str
) -> None:
    sink: list[SinkItem] = []

    result = call(_tracked(sink=sink), _tracked_int(sink))

    # str's own answer, plain, and the line names the method or the operator. str reads a
    # tracked int or bool as a position without asking it anything, so it records nothing
    assert result == call("abcb", 1)
    assert not isinstance(result, ConcolicStr | ConcolicBool)
    assert sink == [Downgrade(name=name)]


def test_a_replace_with_a_tracked_old_string_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    old = ConcolicStr("b", expression="t", sink=sink)

    result = _tracked(sink=sink).replace(old, "x")

    # cvc5 leaves s as it is for an empty old string, where Python puts the new one between
    # every character, and a tracked old string may be empty
    assert result == "axcx"
    assert not isinstance(result, ConcolicStr)
    assert sink == [Downgrade(name="replace")]


# a piece given what str refuses: the call, and the error str raises for it
REFUSED: dict[str, tuple[Callable[[str], object], type[Exception]]] = {
    "s + 1": (lambda s: s + 1, TypeError),  # pyrefly: ignore[unsupported-operation]
    "s['a']": (lambda s: s["a"], TypeError),  # pyrefly: ignore[bad-index]
    "s.replace(1, 'x')": (lambda s: s.replace(1, "x"), TypeError),  # pyrefly: ignore[no-matching-overload]
    "s.removeprefix(1)": (lambda s: s.removeprefix(1), TypeError),  # pyrefly: ignore[no-matching-overload]
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


@pytest.mark.skipif(sys.version_info >= (3, 13), reason="replace takes a keyword count from 3.13")
def test_a_keyword_goes_to_strs_own_replace_and_records_nothing() -> None:
    sink: list[SinkItem] = []

    # a keyword is a form pyct does not encode, and str's replace refuses it on the 3.12 floor,
    # in its own words and as the target's raise
    with pytest.raises(TypeError) as plain:
        "abcb".replace("b", "x", count=1)  # pyrefly: ignore[no-matching-overload]
    with pytest.raises(TypeError) as raised:
        _tracked(sink=sink).replace("b", "x", count=1)  # pyrefly: ignore[unexpected-keyword]

    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


# a right side with its own __radd__ that answers: the call, and the same call on a plain str
ANSWERED_BY_THE_RIGHT: dict[str, Callable[[str], object]] = {
    "s + Escaped('<b>')": lambda s: s + Escaped("<b>"),
    "s + Column()": lambda s: s + Column(),  # pyrefly: ignore[unsupported-operation]
}


@pytest.mark.parametrize("call", ANSWERED_BY_THE_RIGHT.values(), ids=list(ANSWERED_BY_THE_RIGHT))
def test_a_right_side_with_its_own_reflected_plus_answers_as_it_would_for_str(
    call: Callable[[str], object],
) -> None:
    sink: list[SinkItem] = []

    joined = call(_tracked(sink=sink))

    # Python asks the right side's __radd__ before str joins a plain str to it, so that
    # __radd__ answers here too, as it does for "abcb" on the left
    assert joined == call("abcb")
    assert sink == []


def test_a_right_side_whose_reflected_plus_declines_is_joined_by_str() -> None:
    sink: list[SinkItem] = []

    joined = _tracked(sink=sink) + Declining("x")

    # the __radd__ hands the join back, so str's own concatenation answers, followed
    assert isinstance(joined, ConcolicStr)
    assert str.__eq__(joined, "abcb" + Declining("x")) is True
    assert joined.expression == ["+", "s", "'x'"]
    assert sink == []


def test_a_number_on_the_left_of_plus_is_refused_by_python_and_records_nothing() -> None:
    sink: list[SinkItem] = []

    # the reflected method hands the number back to Python, which refuses int + str itself
    with pytest.raises(TypeError) as plain:
        operator.add(1, "abcb")  # pyrefly: ignore[no-matching-overload]
    with pytest.raises(TypeError) as raised:
        1 + _tracked(sink=sink)  # pyrefly: ignore[unsupported-operation]

    # Python's own sentence, naming the tracked str's type where plain Python names str
    assert str(raised.value) == str(plain.value).replace("'str'", "'ConcolicStr'")
    assert sink == []
