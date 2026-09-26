import copy
import dataclasses
import types
from collections.abc import Callable

import pytest

from pyct.core import bools, strs, values
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target

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


# each compare against a literal holding U+30000, one past the last character cvc5 holds, and
# the dunder that names the downgrade; the answer is str's own for s = "abc"
PAST_THE_LAST_CHARACTER: dict[str, tuple[Callable[[str], object], bool]] = {
    "__lt__": (lambda s: s < "a\U00030000", True),
    "__le__": (lambda s: s <= "a\U00030000", True),
    "__gt__": (lambda s: s > "a\U00030000", False),
    "__ge__": (lambda s: s >= "a\U00030000", False),
    "__eq__": (lambda s: s == "a\U00030000", False),
    "__ne__": (lambda s: s != "a\U00030000", True),
}


@pytest.mark.parametrize(
    ("name", "case"), PAST_THE_LAST_CHARACTER.items(), ids=list(PAST_THE_LAST_CHARACTER)
)
def test_a_literal_past_the_last_character_is_strs_own_compare_and_a_downgrade(
    name: str, case: tuple[Callable[[str], object], bool]
) -> None:
    call, answer = case
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    result = call(s)

    assert result is answer
    assert sink == [Downgrade(name=name)]


def test_a_literal_up_to_the_last_character_is_followed() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    result = s == "a\U0002ffff"

    assert isinstance(result, ConcolicBool)
    assert result.expression == ["==", "s", repr("a\U0002ffff")]
    assert sink == []


def test_a_tracked_str_holding_a_character_past_the_last_is_still_followed() -> None:
    # the solver reads the expression, never the value, so the value may hold any character
    sink: list[SinkItem] = []
    s = ConcolicStr("\U00030000", expression="s", sink=sink)
    t = ConcolicStr("\U00030000", expression="t", sink=sink)

    assert isinstance(s == "abc", ConcolicBool)
    assert isinstance(s == t, ConcolicBool)
    assert sink == []


def test_a_concolic_str_hashes_as_its_value() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    # a class body that defines __eq__ loses __hash__ unless it keeps str's
    assert hash(s) == hash("abc")


# a probe whose text is fixed here, so the line and column of the fork are exact
PROBE = "def probe(v):\n    if v:\n        return 'yes'\n    return 'no'\n"


def _probe() -> Callable[[object], object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


@pytest.mark.parametrize(("value", "taken"), [("abc", True), ("", False)])
def test_the_truth_test_records_the_fork_against_the_empty_string(value: str, taken: bool) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr(value, expression="s", sink=sink)

    answer = _probe()(s)

    # the empty string is the one value that takes the other side, as zero is for an int
    assert answer == ("yes" if taken else "no")
    assert sink == [
        Branch(expression=["!=", "s", "''"], taken=taken, site=Site(file="<probe>", line=2, col=7))
    ]


def test_the_truth_test_answers_with_a_real_bool() -> None:
    s = ConcolicStr("abc", expression="s", sink=[])

    assert s.__bool__() is True


# a spread of what ConcolicStr has not taught: the call, and the name its downgrade carries.
# A method is named by its own name and an operator by its dunder
DOWNGRADED_CALLS: dict[str, tuple[Callable[[str], object], str]] = {
    "s.encode()": (lambda s: s.encode(), "encode"),
    "s.upper()": (lambda s: s.upper(), "upper"),
    "s.split()": (lambda s: s.split(), "split"),
    "len(s)": (len, "__len__"),
    "str(s)": (str, "__str__"),
    "s[0]": (lambda s: s[0], "__getitem__"),
    "s.expandtabs()": (lambda s: s.expandtabs(), "expandtabs"),
    "s + 'x'": (lambda s: s + "x", "__add__"),
    "s * 2": (lambda s: s * 2, "__mul__"),
    "next(iter(s))": (lambda s: next(iter(s)), "__iter__"),
}

# what stays str's own and records nothing: a dict key, a debugger's read, pickling, the size
KEPT_CALLS: dict[str, Callable[[str], object]] = {
    "hash(s)": hash,
    "repr(s)": repr,
    "s.__getnewargs__()": lambda s: s.__getnewargs__(),
    "s.__sizeof__()": lambda s: s.__sizeof__(),
}


@pytest.mark.parametrize(("call", "name"), DOWNGRADED_CALLS.values(), ids=list(DOWNGRADED_CALLS))
def test_an_untaught_operation_is_strs_own_and_a_downgrade(
    call: Callable[[str], object], name: str
) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    result = call(s)

    # str's own answer, plain: nothing in it carries the condition on
    assert result == call("abc")
    assert not isinstance(result, ConcolicStr | ConcolicBool)
    assert sink == [Downgrade(name=name)]


@pytest.mark.parametrize("call", KEPT_CALLS.values(), ids=list(KEPT_CALLS))
def test_a_kept_operation_is_strs_own_and_records_nothing(call: Callable[[str], object]) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    call(s)

    assert sink == []


@dataclasses.dataclass
class Holder:
    """A dataclass the target keeps a str in."""

    name: str


# copy, deepcopy and asdict, each on data holding a tracked str: the call, and the str it hands back
COPIES: dict[str, Callable[[str], object]] = {
    "copy.copy(s)": copy.copy,
    "copy.deepcopy(s)": copy.deepcopy,
    "copy.deepcopy({'name': s})": lambda s: copy.deepcopy({"name": s})["name"],
    "dataclasses.asdict(Holder(s))": lambda s: dataclasses.asdict(Holder(s))["name"],
}


@pytest.mark.parametrize("call", COPIES.values(), ids=list(COPIES))
def test_a_copy_of_a_concolic_str_is_the_value_itself(call: Callable[[str], object]) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    copied = call(s)

    # copy hands a plain str back as it is, because a str cannot change; a tracked one comes
    # back the same way, its expression and sink with it, so nothing is lost
    assert copied is s
    assert sink == []


def test_an_f_string_records_str_and_then_format() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    # with no format spec, str's __format__ asks for __str__ itself before it returns
    assert f"{s}" == "abc"
    assert sink == [Downgrade(name="__str__"), Downgrade(name="__format__")]


def test_a_raise_under_an_untaught_method_is_the_targets_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    with pytest.raises(LookupError, match="unknown encoding") as raised:
        s.encode("no-such-codec")

    assert raised_by_target(raised.value)
    assert sink == []


# a keyword each downgraded str method takes: the call, and the name its downgrade carries. The
# value has two commas, a tab, a newline and a field, so each keyword changes str's answer
KEYWORD_CALLS: dict[str, tuple[Callable[[str], object], str]] = {
    's.split(sep=",")': (lambda s: s.split(sep=","), "split"),
    's.split(",", maxsplit=1)': (lambda s: s.split(",", maxsplit=1), "split"),
    's.rsplit(sep=",")': (lambda s: s.rsplit(sep=","), "rsplit"),
    "s.splitlines(keepends=True)": (lambda s: s.splitlines(keepends=True), "splitlines"),
    's.encode(encoding="utf-16")': (lambda s: s.encode(encoding="utf-16"), "encode"),
    "s.expandtabs(tabsize=4)": (lambda s: s.expandtabs(tabsize=4), "expandtabs"),
    "s.format(x=1)": (lambda s: s.format(x=1), "format"),
}


@pytest.mark.parametrize(("call", "name"), KEYWORD_CALLS.values(), ids=list(KEYWORD_CALLS))
def test_a_keyword_to_an_untaught_method_is_strs_own_and_a_downgrade(
    call: Callable[[str], object], name: str
) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("a,b\t{x},c\n", expression="s", sink=sink)

    # the keyword reaches str's own method as the target wrote it
    assert call(s) == call("a,b\t{x},c\n")
    assert sink == [Downgrade(name=name)]


def test_a_keyword_named_like_pycts_own_parameters_reaches_strs_own_method() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("{self}-{operation}", expression="s", sink=sink)

    # self and operation are the names pyct's wrappers give the receiver and the method; a
    # target keyword of either name still reaches str's own format as the target wrote it
    assert s.format(self=1, operation=2) == "1-2"  # pyrefly: ignore[no-matching-overload]
    assert sink == [Downgrade(name="format")]


# a keyword str's own method refuses: one encode names nowhere, and one to a taught search,
# whose str method takes none; index is the search that forks before it may raise, and self
# is the name pyct's search gives its receiver
REFUSED_KEYWORDS: dict[str, Callable[[str], object]] = {
    "s.encode(bogus=1)": lambda s: s.encode(bogus=1),  # pyrefly: ignore[unexpected-keyword]
    's.find("x", start=1)': lambda s: s.find("x", start=1),  # pyrefly: ignore[unexpected-keyword]
    's.index("x", start=1)': lambda s: s.index("x", start=1),  # pyrefly: ignore[unexpected-keyword]
    's.find("x", self=1)': lambda s: s.find("x", self=1),  # pyrefly: ignore[unexpected-keyword]
}


@pytest.mark.parametrize("call", REFUSED_KEYWORDS.values(), ids=list(REFUSED_KEYWORDS))
def test_a_keyword_str_refuses_is_strs_own_raise_and_records_nothing(
    call: Callable[[str], object],
) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr("abc", expression="s", sink=sink)

    with pytest.raises(TypeError) as plain:
        call("abc")
    with pytest.raises(TypeError) as raised:
        call(s)

    # str's own sentence, the one plain Python gives, and never one naming pyct's code
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == []


def _derived_downgrades() -> set[str]:
    """The names the derivation wrapped: what `downgraded` built, and nothing else on the class."""
    return {
        name
        for name, member in vars(ConcolicStr).items()
        if getattr(member, "__qualname__", "").startswith("downgraded.")
    }


def test_the_derivation_downgrades_every_str_method_but_the_taught_and_the_kept() -> None:
    methods = {
        name
        for name, member in vars(str).items()
        if isinstance(
            member, types.FunctionType | types.WrapperDescriptorType | types.MethodDescriptorType
        )
    }

    compares = {"__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__"}
    searches = {"__contains__", "startswith", "endswith", "count"}
    positions = {"find", "index", "rfind", "rindex"}
    kept = {"__hash__", "__repr__", "__getnewargs__", "__sizeof__"}

    # whatever str defines on the Python that runs this, the only methods left unwrapped are
    # the six compares and the searches taught above and the four str keeps
    assert methods - _derived_downgrades() == compares | searches | positions | kept
    assert _derived_downgrades().isdisjoint(strs._KEPT)


def test_every_operation_that_reaches_strs_own_goes_through_the_helper() -> None:
    # a call into str written without the helper leaves its raise blamed on pyct, silently.
    # ConcolicStr's methods, operators and plain names alike, are written in three files: its
    # own, bools for the compare closures and values for the downgrade closures, so the scan
    # covers all three. A compare or a search in strs hands the call to a closure it holds, so
    # what a function holds counts as what it calls
    written_here = {
        name: member
        for name, member in vars(ConcolicStr).items()
        if (code := getattr(member, "__code__", None)) is not None
        and code.co_filename in {strs.__file__, bools.__file__, values.__file__}
    }

    without_the_helper = {
        name for name, member in written_here.items() if not _reaches_through_the_helper(member)
    }

    # the scan read the taught compares, the truth test and the searches, and a derived plain
    # method, so an empty answer is not an empty scan
    assert {"__lt__", "__le__", "__gt__", "__ge__", "__eq__", "__ne__", "__bool__"} <= (
        written_here.keys()
    )
    assert {"find", "encode"} <= written_here.keys()
    # these hand the value itself back and never call str, so they have nothing to guard
    assert without_the_helper == {"__copy__", "__deepcopy__"}


def _reaches_through_the_helper(function: object) -> bool:
    """Whether a function calls `own`, or holds a function that does, the way a closure does."""
    code = getattr(function, "__code__", None)
    if code is None:
        return False
    if "own" in code.co_names:
        return True
    held = [cell.cell_contents for cell in getattr(function, "__closure__", None) or ()]
    return any(_reaches_through_the_helper(inner) for inner in held)
