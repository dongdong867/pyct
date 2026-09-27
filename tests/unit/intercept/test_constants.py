"""Which names a module binds to literals alone, which the rules read as they read a literal."""

import ast

import pytest

from pyct.intercept.constants import literal_names
from tests.unit.intercept.test_substitute import substituted


def kinds(source: str) -> dict[str, frozenset[type]]:
    return literal_names(ast.parse(source)).kinds


def test_a_name_bound_to_literals_alone_holds_their_kinds() -> None:
    source = "RATE = 0.5\nFLAG: bool = True\ndef f():\n    RATE = 1.5\n    TEXT = 'x'\n"

    assert kinds(source) == {
        "RATE": frozenset({float}),
        "FLAG": frozenset({bool}),
        "TEXT": frozenset({str}),
    }


def test_a_name_bound_to_literals_of_two_kinds_holds_both() -> None:
    assert kinds("A = 0.5\nA = True\n") == {"A": frozenset({float, bool})}


@pytest.mark.parametrize(
    "binding",
    [
        "RATE = f()",
        "RATE += 1.0",
        "RATE, other = 0.5, 1",
        "RATE = other = 0.5",
        "for RATE in xs:\n    pass",
        "with cm() as RATE:\n    pass",
        "import RATE",
        "from m import x as RATE",
        "def RATE():\n    pass",
        "class RATE:\n    pass",
        "def f(RATE):\n    pass",
        "def f(*, RATE=0.5):\n    pass",
        "lambda RATE: 0",
        "[0 for RATE in xs]",
        "(RATE := 0.5)",
        "del RATE",
        "try:\n    pass\nexcept E as RATE:\n    pass",
        "match v:\n    case [*RATE]:\n        pass",
        "match v:\n    case {**RATE}:\n        pass",
        "match v:\n    case RATE:\n        pass",
        "RATE: float",
    ],
)
def test_any_other_binding_anywhere_in_the_module_makes_the_name_not_count(binding: str) -> None:
    source = "RATE = 0.5\n" + binding + "\n"

    assert "RATE" not in kinds(source)


def test_a_read_directly_in_a_class_body_is_told_apart() -> None:
    tree = ast.parse("RATE = 0.5\nclass C:\n    a = RATE\n    def f(self):\n        return RATE\n")
    found = literal_names(tree)
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "RATE"]
    loads = [node for node in reads if isinstance(node.ctx, ast.Load)]

    assert [id(node) in found.in_class for node in loads] == [True, False]


def test_an_operator_with_a_name_bound_to_a_float_on_the_left_hands_its_right_side_over() -> None:
    source = "RATE = 0.5\ndef f(n):\n    return RATE * n\n"

    assert "return RATE * __pyct_handed__(n, RATE)" in substituted(source)


def test_a_name_read_in_a_class_body_or_bound_otherwise_is_left_as_written() -> None:
    assert "__pyct_handed__" not in substituted("RATE = 0.5\nclass C:\n    x = RATE * n\n")
    assert "__pyct_handed__" not in substituted("RATE = 0.5\nRATE = f()\ny = RATE * n\n")
    assert "__pyct_handed__" not in substituted("NAME = 'x'\ny = NAME * n\n")


def test_a_method_on_a_name_bound_to_str_literals_is_substituted() -> None:
    source = "def f(s):\n    text = 'xyz'\n    return text.find(s)\n"

    assert "return __pyct_method__(text.find, s)" in substituted(source)
    assert "__pyct_method__" not in substituted("text = 'x'\ntext = 1.5\ny = text.find(s)\n")
