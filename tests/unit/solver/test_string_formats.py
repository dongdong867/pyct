"""A `%` on a format in SMT-LIB: the concatenation of its literal text and its operands' text,
with cvc5 held against Python's own `%`."""

import pytest

from pyct.core.branch import Expression
from pyct.solver.str_formats import concatenated, is_format
from pyct.solver.str_joins import expanded
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render_lists import answered, fork


def _names(_part: Expression) -> bool:
    return False


@pytest.mark.parametrize(
    ("node", "formats"),
    [
        (["%", "'%s'", "s"], True),
        (["%", '"%s"', "s"], True),
        # an int's remainder: its left side is a number or a name, never a str literal
        (["%", "n", 3], False),
        (["%", 7, "n"], False),
        (["+", "'%s'", "s"], False),
    ],
)
def test_a_format_is_a_percent_whose_left_side_is_a_str_literal(
    node: list[Expression], *, formats: bool
) -> None:
    assert is_format(node) is formats


@pytest.mark.parametrize(
    ("fmt", "operand", "written"),
    [
        ("'%d items'", "n", ["+", ["str", ["int", "n"]], "' items'"]),
        ("'<%s>'", ["()", "s"], ["+", "'<'", ["str", "s"], "'>'"]),
        ("'%i'", "b", ["str", ["int", "b"]]),
        (
            "'%s-%d%%'",
            ["()", "s", 7],
            ["+", ["str", "s"], "'-7%'"],
        ),
        # each plain operand's text is Python's, under its own conversion
        (
            "'%-4s|%s=%03d %r %s'",
            ["()", "'ab'", "k", 5, "'q'", True],
            ["+", "'ab  |'", ["str", "k"], "\"=005 'q' True\""],
        ),
        ("'%s%s'", ["()", "a", "b"], ["+", ["str", "a"], ["str", "b"]]),
        ("'%s'", ["()", "'x'"], "'x'"),
        ("''", ["()"], "''"),
    ],
)
def test_a_format_is_its_literal_text_and_its_operands_text_joined(
    fmt: str, operand: Expression, written: Expression
) -> None:
    assert concatenated(fmt, operand) == written


def test_a_format_no_conversion_reads_one_to_one_is_a_pyct_bug() -> None:
    with pytest.raises(ValueError, match="reads no operand one to one"):
        concatenated("'%(k)s'", "d")


def test_a_path_writes_each_format_out_and_keeps_an_int_s_remainder() -> None:
    formatted: Expression = ["%", "'<%s>'", ["()", "s"]]
    remainder: Expression = ["==", ["%", "n", 2], 0]
    prefix = (fork(["==", formatted, "'<a>'"]), fork(remainder))

    written = [branch.expression for branch in expanded(prefix, _names)]

    assert written == [["==", ["+", "'<'", ["str", "s"], "'>'"], "'<a>'"], remainder]


@needs_cvc5
@pytest.mark.parametrize(
    ("args", "fmt", "operand", "wanted"),
    [
        ({"s": "x", "n": 0}, "'%s=%d;'", ["()", "s", "n"], "key=-42;"),
        ({"n": 0}, "'%d items'", "n", "3 items"),
        ({"b": False, "n": 0}, "'%d/%s/%i'", ["()", "b", "b", "n"], "1/True/7"),
        ({"s": "x"}, "'%s-%d%%'", ["()", "s", 7], "ab-7%"),
    ],
    ids=["str and int", "int alone", "bool both ways", "plain operand and percent sign"],
)
def test_cvc5_formats_as_python_does(
    args: dict[str, object], fmt: str, operand: Expression, wanted: str
) -> None:
    answer = answered(args, fork(["==", ["%", fmt, operand], repr(wanted)]))

    items = operand[1:] if isinstance(operand, list) else [operand]
    values = tuple(answer.get(item, item) for item in items)  # pyrefly: ignore
    assert eval(fmt) % values == wanted  # noqa: S307 - a format literal of this table
