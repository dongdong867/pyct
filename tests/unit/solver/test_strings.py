import shutil

import pytest

from pyct.core.branch import Branch, Site
from pyct.solver.answer import Sat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import decode, encode

# a Python str, and the SMT-LIB literal it is written as: printable ASCII as itself, a double
# quote twice, and everything else, the backslash included, as its code point in hex
LITERALS: dict[str, tuple[str, str]] = {
    "empty": ("", '""'),
    "printable": ("abc XYZ 09 ~!", '"abc XYZ 09 ~!"'),
    "single-quote": ("it's", '"it\'s"'),
    "double-quote": ('say "hi"', '"say ""hi"""'),
    "backslash": ("a\\b", '"a\\u{5c}b"'),
    "tab": ("a\tb", '"a\\u{9}b"'),
    "newline": ("a\nb", '"a\\u{a}b"'),
    "nul": ("\x00", '"\\u{0}"'),
    "delete": ("\x7f", '"\\u{7f}"'),
    "past-ascii": ("é", '"\\u{e9}"'),
    "emoji": ("\U0001f600", '"\\u{1f600}"'),
    "last-character": ("\U0002ffff", '"\\u{2ffff}"'),
    "the-story's-literal": ('a\nb"c\\d é', '"a\\u{a}b""c\\u{5c}d \\u{e9}"'),
}


@pytest.mark.parametrize(("value", "literal"), LITERALS.values(), ids=list(LITERALS))
def test_a_str_is_written_as_the_literal_cvc5_reads(value: str, literal: str) -> None:
    assert encode(value) == literal


@pytest.mark.parametrize(("value", "literal"), LITERALS.values(), ids=list(LITERALS))
def test_a_literal_cvc5_prints_is_read_back_as_the_same_str(value: str, literal: str) -> None:
    assert decode(literal) == value


def test_a_character_past_the_last_one_cvc5_holds_is_refused() -> None:
    with pytest.raises(ValueError, match="U\\+30000"):
        encode("a\U00030000")


# what cvc5 never prints: a bare quote or backslash inside, an escape it does not write, a
# character it escapes, a code point past its last, and a value that is not quoted at all
UNREADABLE: dict[str, str] = {
    "lone-quote": '"a"b"',
    "lone-backslash": '"a\\b"',
    "four-digit-escape": '"\\u00e9"',
    "upper-case-hex": '"\\u{E9}"',
    "six-digit-escape": '"\\u{10000a}"',
    "past-the-last-character": '"\\u{30000}"',
    "raw-tab": '"a\tb"',
    "raw-past-ascii": '"é"',
    "unquoted": "abc",
    "one-quote": '"',
}


@pytest.mark.parametrize("literal", UNREADABLE.values(), ids=list(UNREADABLE))
def test_a_literal_cvc5_would_not_print_is_an_error(literal: str) -> None:
    with pytest.raises(ValueError, match="cvc5"):
        decode(literal)


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
@pytest.mark.parametrize("value", [value for value, _ in LITERALS.values()], ids=list(LITERALS))
def test_the_real_cvc5_hands_back_the_str_it_was_given(value: str) -> None:
    equal = Branch(expression=["==", "s", repr(value)], taken=True, site=Site("m.py", 2, 7))

    assert solve((equal,), {"s": str}, None) == Sat({"s": value})
