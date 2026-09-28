"""A plain str operand of a subclass with its own `__iter__`: the solver reads its text through
str's own walk, so the subclass's walk never runs, and each operation gives plain Python's
answer with the operand written as its plain text."""

import json

from pyct.core.branch import SinkItem
from pyct.core.str_joins import joined
from pyct.core.str_operands import literal, within_cvc5
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_substitutes import expressions


class OwnIter(str):
    """A str whose own walk hands out something else, which str's own operations never run."""

    def __iter__(self):  # noqa: ANN204
        return iter(["zz"])


def tracked(value: str, sink: list[SinkItem]) -> ConcolicStr:
    return ConcolicStr.made(value, expression="s", sink=sink)


def written(value: object) -> str:
    """A fork's expression or a tracked value's form, as text to look for a literal in."""
    return json.dumps(value)


def test_the_characters_are_read_through_str_s_own_walk() -> None:
    assert within_cvc5(OwnIter("a")) is True
    assert within_cvc5(OwnIter("\U00030000")) is False


def test_the_literal_is_its_plain_text() -> None:
    assert literal(OwnIter("a"), ConcolicStr) == "'a'"


def test_equality_records_its_fork() -> None:
    sink: list[SinkItem] = []

    assert bool(tracked("a", sink) == OwnIter("a")) == ("a" == OwnIter("a"))
    assert expressions(sink) == [(["==", "s", "'a'"], True)]


def test_an_order_compare_records_its_fork() -> None:
    sink: list[SinkItem] = []

    assert bool(tracked("a", sink) < OwnIter("b")) == ("a" < OwnIter("b"))
    assert expressions(sink) == [(["<", "s", "'b'"], True)]


def test_startswith_reads_the_prefix_as_its_text() -> None:
    sink: list[SinkItem] = []

    assert bool(tracked("ab", sink).startswith(OwnIter("a"))) == "ab".startswith(OwnIter("a"))
    [(expression, _)] = expressions(sink)
    assert "'a'" in written(expression)


def test_find_reads_the_needle_as_its_text() -> None:
    sink: list[SinkItem] = []

    found = tracked("ab", sink).find(OwnIter("b"))
    assert int(found) == "ab".find(OwnIter("b"))
    assert "'b'" in written(found.expression)  # pyrefly: ignore[missing-attribute]


def test_a_join_writes_the_item_as_its_text() -> None:
    sink: list[SinkItem] = []

    result = joined("-", [tracked("a", sink), OwnIter("b")], ConcolicStr)
    assert result == "-".join(["a", OwnIter("b")])
    assert "'b'" in written(result.expression)  # pyrefly: ignore[missing-attribute]
