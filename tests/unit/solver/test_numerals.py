"""cvc5 held against Python where a string is read as a number: `int(s)` and `float(s)`."""

import re
import sys

import pytest

from pyct.solver import numerals
from pyct.solver.floats import literal
from pyct.solver.strings import encode
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_float_agreement import _same
from tests.unit.solver.test_float_int_agreement import _values

# texts Python reads as an int, and texts it refuses, around each rule of its grammar: the spaces
# it strips, a sign, underscores between digits, and the digits it counts against its limit
INT_TEXTS = [
    "0",
    "7",
    "-7",
    "+7",
    " 12 ",
    "\t-1_0\n",
    "\x0b\x0c\r3",
    "007",
    "0_0",
    "1_000_000",
    "9" * 30,
    "",
    " ",
    "+",
    "-",
    "_1",
    "1_",
    "1__0",
    "+_1",
    "1 2",
    "- 1",
    "+-1",
    "--1",
    "\x1c1",
    "1e3",
    "0x10",
    "12a",
    "1.0",
]

# texts Python reads as a float and texts it refuses: each form of a decimal, an exponent, the
# infinities and NaN in any case, underscores, spaces, and values that round
FLOAT_TEXTS = [
    "0",
    "-0",
    "1.5",
    "-1.5",
    ".5",
    "5.",
    "-.5",
    "0.1",
    "123.456",
    "0.30000000000000004",
    "9007199254740993",
    "9007199254740993.5",
    "1" * 400,
    "1e5",
    "1E-5",
    "5.e3",
    "  2.5  ",
    "1_0.5",
    "1.5_0",
    "1e1_0",
    "1_000.000_1e+0_1",
    "1e400",
    "1e-400",
    "4.9e-324",
    "inf",
    "-inf",
    "+Infinity",
    "iNfInItY",
    "nan",
    "-nan",
    "NaN",
    "0.0000000000000000000001",
    "",
    ".",
    "-.",
    "1._5",
    "1e",
    "e1",
    "1.5.2",
    "infinit",
    "nan1",
    "1 .5",
    "0x1p3",
    "\x1c1.5",
]


def _read(read: type, text: str) -> object:
    try:
        return read(text)
    except ValueError:
        return None


# the texts float_of reads exactly: digits, a point and a fraction, after a minus, and nan and inf
_PLAIN = re.compile(r"-?(\d+(\.\d*)?|\.\d+|nan|inf)", re.ASCII)


def _inside(text: str) -> bool:
    """Whether a text is inside the bound float_of is exact in, as Python has it."""
    if _PLAIN.fullmatch(text) is None:
        return False
    whole, _, fraction = text.removeprefix("-").partition(".")
    if text.removeprefix("-") in ("nan", "inf") or not fraction:
        return True
    return len(fraction) <= 22 and int(whole + fraction) <= 2**53


@needs_cvc5
def test_cvc5_accepts_exactly_the_ascii_texts_python_reads_as_an_int() -> None:
    said = _values("Bool", [numerals.is_int(encode(text)) for text in INT_TEXTS])

    assert said == [_read(int, text) is not None for text in INT_TEXTS]


@needs_cvc5
def test_cvc5_reads_each_int_text_as_python_does() -> None:
    texts = [text for text in INT_TEXTS if _read(int, text) is not None]

    said = _values("Int", [numerals.int_of(encode(text)) for text in texts])

    assert said == [int(text) for text in texts]


def test_python_counts_the_digits_of_an_int_text_against_its_limit() -> None:
    most = sys.get_int_max_str_digits()

    # the digits alone count: leading zeros do, and underscores, spaces and a sign do not
    assert int("1" * most) > 0
    assert int(" -" + "1_" * (most - 1) + "1 ") < 0
    for past in ("1" * (most + 1), "0" * (most + 1)):
        with pytest.raises(ValueError, match="Exceeds the limit"):
            int(past)


@needs_cvc5
@pytest.mark.parametrize(
    ("most", "held"),
    [(5, [True, True, True, False, False]), (0, [True] * 5)],
)
def test_cvc5_counts_the_digits_of_an_int_text_as_python_does(
    monkeypatch: pytest.MonkeyPatch, most: int, held: list[bool]
) -> None:
    # a limit of five stands in for Python's 4300, which cvc5 reads slowly; zero is no limit
    monkeypatch.setattr(sys, "get_int_max_str_digits", lambda: most)
    texts = ["12345", "1_2_3_4_5", " -12345 ", "123456", "000001"]

    said = _values("Bool", [numerals.is_int(encode(text)) for text in texts])

    assert said == held


@needs_cvc5
def test_a_text_past_ascii_reads_as_no_number() -> None:
    # Python reads Arabic-Indic digits and a no-break space; the encoding is exact for ASCII
    texts = ["١٢", "\xa012"]

    said = _values("Bool", [numerals.is_int(encode(text)) for text in texts])

    assert said == [False, False]
    assert [int(text) for text in texts] == [12, 12]


@needs_cvc5
def test_cvc5_accepts_exactly_the_ascii_texts_python_reads_as_a_float() -> None:
    said = _values("Bool", [numerals.is_float(encode(text)) for text in FLOAT_TEXTS])

    assert said == [_read(float, text) is not None for text in FLOAT_TEXTS]


@needs_cvc5
def test_cvc5_reads_each_float_text_inside_its_bound_as_python_does_to_the_bit() -> None:
    texts = [text for text in FLOAT_TEXTS if _read(float, text) is not None]
    written = [numerals.float_of(encode(text), "past") for text in texts]

    values = _values("Float64", [term for term, _ in written], "(declare-const past Float64)")
    bounds = _values("Bool", [bound for _, bound in written], "(declare-const past Float64)")

    assert bounds == [_inside(text) for text in texts]
    wrong = [
        (text, value)
        for text, value, inside in zip(texts, values, bounds, strict=True)
        if inside and not _same(value, float(text))
    ]
    assert wrong == []
    # the texts reach past the bound too, so a clean result is not a narrow one
    assert False in bounds


@needs_cvc5
def test_past_its_bound_float_of_a_text_can_be_every_value_python_reads() -> None:
    texts = [text for text in FLOAT_TEXTS if _read(float, text) is not None]
    texts = [text for text in texts if not _inside(text)]
    written = [numerals.float_of(encode(text), literal(float(text))) for text in texts]

    values = _values("Float64", [term for term, _ in written])

    assert [_same(value, float(text)) for value, text in zip(values, texts, strict=True)] == [
        True
    ] * len(texts)


@needs_cvc5
def test_without_a_constant_past_its_bound_float_of_a_text_is_the_exact_term() -> None:
    term, bound = numerals.float_of(encode("2.5"))

    assert _values("Float64", [term]) == [2.5]
    assert _values("Bool", [bound]) == [True]
