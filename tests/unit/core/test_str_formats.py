"""`%` formatting with a plain str format and a tracked operand: the text Python gives, tracked
where pyct follows each tracked operand's conversion, and a `__mod__` downgrade elsewhere."""

import operator
from collections.abc import Callable
from typing import Any
from unittest.mock import ANY

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, SinkItem
from pyct.core.dicts import ConcolicDict
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.lists import ConcolicList
from pyct.core.str_formats import (
    Spec,
    formatted,
    formatter,
    fstring_mod,
    holds_tracked,
    in_place_formatter,
    mod,
    tokens,
)
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target


def _tracked(sink: list[SinkItem]) -> dict[str, Any]:
    """A tracked str, int, bool and float, each named by its kind, on one sink."""
    return {
        "s": ConcolicStr.made("ab", expression="s", sink=sink),
        "n": ConcolicInt.made(-7, expression="n", sink=sink),
        "b": ConcolicBool.made(True, expression="b", sink=sink),
        "f": ConcolicFloat.made(2.5, expression="f", sink=sink),
    }


def _raised(call: Callable[[], object]) -> tuple[type, str]:
    with pytest.raises(Exception) as raised:  # noqa: PT011 - any raise is the answer
        call()
    return type(raised.value), str(raised.value)


@pytest.mark.parametrize(
    ("fmt", "read"),
    [
        ("%s-%d%%", (Spec("%s", "s", True), "-", Spec("%d", "d", True), "%")),
        ("x%5.2fy%-3i", ("x", Spec("%5.2f", "f", False), "y", Spec("%-3i", "i", False))),
        ("%%s", ("%", "s")),
        ("", ()),
        # a key, a `*`, an odd `%` and a letter Python refuses read no operand one to one
        ("%(k)s", None),
        ("%(k)s%s", None),
        ("%*d", None),
        ("a%", None),
        ("%5%", None),
        ("%z", None),
    ],
)
def test_a_format_reads_as_its_text_and_its_conversions(
    fmt: str, read: tuple[object, ...] | None
) -> None:
    assert tokens(fmt) == read


# a format, its operand written with the tracked values by name, the expression the answer
# carries, and the text Python gives
FOLLOWED: dict[str, tuple[str, Callable[[dict[str, Any]], object], object]] = {
    "a tuple": ("<%s|%d>", lambda t: (t["s"], t["n"]), ["%", "'<%s|%d>'", ["()", "s", "n"]]),
    "one operand": ("%d items", lambda t: t["n"], ["%", "'%d items'", "n"]),
    "a bool both ways": ("%s/%i", lambda t: (t["b"], t["b"]), ["%", "'%s/%i'", ["()", "b", "b"]]),
    "plain operands": (
        "%s %r %d %s %%",
        lambda t: (t["s"], "q", 3, True),
        ["%", "'%s %r %d %s %%'", ["()", "s", "'q'", 3, True]],
    ),
    # another plain operand is written into the format as the text it gave, a `%` doubled
    "a float written in": (
        "%s=%.1f%s",
        lambda t: (t["s"], 0.25, 9.5),
        ["%", "'%s=0.29.5'", ["()", "s"]],
    ),
    "a namedtuple-like tuple": (
        "%s%s",
        lambda t: _Pair(t["s"], "x"),
        ["%", "'%s%s'", ["()", "s", "'x'"]],
    ),
}


class _Pair(tuple[object, ...]):
    def __new__(cls, *items: object) -> "_Pair":
        return super().__new__(cls, items)


@pytest.mark.parametrize(("fmt", "right", "expression"), FOLLOWED.values(), ids=list(FOLLOWED))
def test_a_followed_format_is_python_s_text_tracked(
    fmt: str, right: Callable[[dict[str, Any]], object], expression: object
) -> None:
    sink: list[SinkItem] = []
    tracked = _tracked(sink)
    plain = _tracked([])

    answer = formatted(fmt, right(tracked))

    assert type(answer) is ConcolicStr
    assert str.__str__(answer) == fmt % _plain_values(right(plain))
    assert answer.expression == expression  # pyrefly: ignore[missing-attribute]
    assert sink == []


def _plain_values(right: object) -> object:
    """What plain Python formats: each tracked value as its plain value."""
    if isinstance(right, tuple):
        return tuple(_plain_value(item) for item in right)
    return _plain_value(right)


def _plain_value(item: object) -> object:
    for kind in (bool, int, float, str):
        if isinstance(item, kind):
            return kind.__new__(kind, item) if kind is not bool else bool(int(item))  # pyrefly: ignore
    return item


def test_a_format_of_s_alone_is_the_operand_s_own_text() -> None:
    sink: list[SinkItem] = []
    t = _tracked(sink)

    assert formatted("%s", (t["s"],)) is t["s"]
    text = formatted("%s", t["n"])
    assert str.__str__(text) == "-7"  # pyrefly: ignore[bad-argument-type]
    assert text.expression == ["str", "n"]  # pyrefly: ignore[missing-attribute]
    assert sink == []


# a format pyct does not follow on a tracked operand, and its right side
DOWNGRADED: dict[str, tuple[str, Callable[[dict[str, Any]], object]]] = {
    "a width": ("%5s", lambda t: (t["s"],)),
    "a flag": ("%+d", lambda t: (t["n"],)),
    "a precision": ("%.1s", lambda t: (t["s"],)),
    "a length": ("%ld", lambda t: (t["n"],)),
    "another letter": ("%x", lambda t: (t["n"],)),
    "repr": ("%r", lambda t: (t["s"],)),
    "a float": ("%s", lambda t: (t["f"],)),
    "a float's own letter": ("<%.2f>", lambda t: (t["f"],)),
    "a key": ("%(k)s!", lambda t: {"k": t["s"]}),
    "a star": ("%*d", lambda t: (3, t["n"])),
    "a list": ("%s", lambda t: (ConcolicList.made([1], "xs", t["s"].sink),)),
}


@pytest.mark.parametrize(("fmt", "right"), DOWNGRADED.values(), ids=list(DOWNGRADED))
def test_any_other_conversion_is_python_s_text_plain_and_a_downgrade(
    fmt: str, right: Callable[[dict[str, Any]], object]
) -> None:
    sink: list[SinkItem] = []

    answer = formatted(fmt, right(_tracked(sink)))

    assert type(answer) is str
    assert answer == fmt % _plain_values(right(_tracked([])))
    assert [item for item in sink if isinstance(item, Downgrade)][-1] == Downgrade(
        name="__mod__", site=ANY
    )


def test_a_format_past_the_solver_s_characters_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("a", expression="s", sink=sink)

    assert formatted("\U00030000%s", (s,)) == "\U00030000a"
    assert formatted("%s%s", (s, "\U00030000")) == "a\U00030000"
    assert sink == [Downgrade(name="__mod__", site=ANY)] * 2


@pytest.mark.parametrize("fmt", ["plain", "%s"])
def test_a_mapping_whose_tracked_value_no_conversion_reads_records_nothing(fmt: str) -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("a", expression="s", sink=sink)

    answer = formatted(fmt, {"k": s})

    assert (answer, type(answer)) == (fmt % {"k": "a"}, str)
    assert sink == []


def test_a_tracked_mapping_read_through_a_key_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    d = ConcolicDict.made({"k": "a"}, expression="d", sink=sink)

    answer = formatted("%(k)s!", d)

    assert (answer, type(answer)) == ("a!", str)
    assert sink[-1] == Downgrade(name="__mod__", site=ANY)


class _Named:
    """An object of the target's own whose text is a tracked str."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name


def test_an_object_s_own_tracked_text_is_written_into_the_format_as_plain_text() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("a", expression="s", sink=sink)
    named = _Named(ConcolicStr.made("b", expression="t", sink=sink))

    answer = formatted("%s-%s", (s, named))

    assert answer.expression == ["%", "'%s-b'", ["()", "s"]]  # pyrefly: ignore[missing-attribute]
    assert str.__str__(answer) == "a-b"  # pyrefly: ignore[bad-argument-type]


@pytest.mark.parametrize(
    ("fmt", "right"),
    [
        ("%d", lambda t: (t["s"],)),
        ("%s %s", lambda t: (t["s"],)),
        ("%s", lambda t: (t["s"], t["n"])),
        ("%c", lambda t: (t["s"],)),
        ("%(k)s", lambda t: (t["s"],)),
        ("%q", lambda t: t["n"]),
        ("%d", lambda t: {"k": t["s"]}),
    ],
)
def test_a_format_python_refuses_raises_python_s_error(
    fmt: str, right: Callable[[dict[str, Any]], object]
) -> None:
    sink: list[SinkItem] = []

    expected = _raised(lambda: fmt % _plain_values(right(_tracked([]))))
    with pytest.raises(expected[0]) as raised:
        formatted(fmt, right(_tracked(sink)))

    assert str(raised.value) == expected[1]
    assert raised_by_target(raised.value)
    assert sink == []


class _Remainder:
    def __mod__(self, other: object) -> object:
        return ("mod", other)

    def __imod__(self, other: object) -> object:
        return ("imod", other)


# a pair the routers hand to Python's own `%` or `%=`: what each meets, plain or tracked
PYTHON_S: dict[str, tuple[object, Callable[[dict[str, Any]], object]]] = {
    "plain str": ("%s=%d", lambda _t: ("k", 1)),
    "bytes": (b"%s", lambda _t: (b"x",)),
    "an int": (7, lambda t: (t["n"],)),
    "a class's own": (_Remainder(), lambda t: (t["s"],)),
    "a str subclass": (type("Text", (str,), {})("%s"), lambda t: (t["n"],)),
}


def _formatted_by(left: object, right: object) -> object:
    return formatter(left)(right)


def _formatted_in_place(left: object, right: object) -> object:
    return in_place_formatter(left)(right)


ROUTERS = [(_formatted_by, operator.mod), (_formatted_in_place, operator.imod)]


@pytest.mark.parametrize(("left", "right"), PYTHON_S.values(), ids=list(PYTHON_S))
@pytest.mark.parametrize(("router", "python"), ROUTERS)
def test_the_routers_hand_any_other_pair_to_python(
    left: object,
    right: Callable[[dict[str, Any]], object],
    router: Callable[[object, object], object],
    python: Callable[[object, object], object],
) -> None:
    sink: list[SinkItem] = []

    def answer(call: Callable[[object, object], object], operand: object) -> object:
        try:
            return call(left, operand)
        except TypeError as error:
            return (TypeError, str(error))

    assert answer(router, right(_tracked(sink))) == answer(python, right(_tracked([])))


@pytest.mark.parametrize("router", [_formatted_by, _formatted_in_place])
def test_a_tracked_format_is_its_own_mod_downgrade(
    router: Callable[[object, object], object],
) -> None:
    sink: list[SinkItem] = []
    fmt = ConcolicStr.made("<%s>", expression="fmt", sink=sink)

    answer = router(fmt, (1,))

    assert (answer, type(answer)) == ("<1>", str)
    assert sink == [Downgrade(name="__mod__", site=ANY)]


def test_the_routers_format_a_plain_format_beside_a_tracked_value() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("ab", expression="s", sink=sink)

    for router in (mod, fstring_mod, _formatted_by, _formatted_in_place):
        answer = router("<%s>", (s,))
        assert answer.expression == ["%", "'<%s>'", ["()", "s"]]  # pyrefly: ignore


class _Text(str):
    """A str of the target's own, which a `__str__` may hand back, and which writes the spec
    its `__format__` is handed."""

    def __format__(self, spec: str) -> str:
        return _Text(f"<{spec}>")


class _Texted:
    def __str__(self) -> str:
        return _Text("named-text")


def test_a_literal_s_format_not_compiled_as_an_f_string_hands_back_python_s_own_text() -> None:
    named = _Texted()

    # Python's `%` hands back the str subclass `__str__` gave as the whole text, and so does pyct's
    assert type("%s" % named) is _Text  # noqa: UP031
    assert type(mod("%s", named)) is _Text


@pytest.mark.parametrize("fmt", ["%s", "%5s", "%.9s", "%r|%-12s"])
def test_an_f_string_s_format_runs_as_cpython_s_f_string(fmt: str) -> None:
    operands = (_Texted(),) * fmt.count("%")
    expected = eval(
        f"lambda *_: {fmt!r} % ({', '.join(f'_[{at}]' for at in range(len(operands)))},)"
    )  # noqa: S307

    answer = fstring_mod(fmt, operands)

    assert (answer, type(answer)) == (expected(*operands), type(expected(*operands)))


@pytest.mark.parametrize(
    ("right", "holds"),
    [
        ("x", False),
        (("x", 1), False),
        ({"k": "x"}, False),
        ([ConcolicStr.made("x", "s", [])], False),
        (ConcolicStr.made("x", "s", []), True),
        (("x", ConcolicInt.made(1, "n", [])), True),
        (_Pair("x", ConcolicInt.made(1, "n", [])), True),
        ({"k": ConcolicStr.made("x", "s", [])}, True),
    ],
)
def test_the_right_side_holds_a_tracked_value_as_itself_a_tuple_s_item_or_a_dict_s_value(
    right: object, *, holds: bool
) -> None:
    assert holds_tracked(right) is holds


def test_a_tracked_str_s_reflected_format_declines_what_is_not_a_str() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("ab", expression="s", sink=sink)

    assert s.__rmod__(5) is NotImplemented
    assert str.__str__(s.__rmod__("<%s>")) == "<ab>"  # pyrefly: ignore[bad-argument-type]
    assert sink == []


def test_a_plain_format_of_a_tracked_str_is_followed_through_its_rmod() -> None:
    sink: list[SinkItem] = []
    s = ConcolicStr.made("abc", expression="s", sink=sink)

    # Python asks a str subclass on the right for its `__rmod__` first (`str_formats`)
    alone = "%s" % s  # noqa: UP031
    text = "<%s>" % s  # noqa: UP031

    assert alone is s
    assert (str.__str__(text), type(text)) == ("<abc>", ConcolicStr)
    assert text.expression == ["%", "'<%s>'", "s"]  # pyrefly: ignore[missing-attribute]
    assert sink == []
