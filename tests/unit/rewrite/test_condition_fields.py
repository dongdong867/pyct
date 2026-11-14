"""A guard on the expression rules a rewrite and a formula share (``pyct.rewrite.condition.
refusal``): each node kind the rules accept has the fields they were written for, so a field a
later Python release adds to one, which the rules would skip and not refuse, fails here."""

import ast
import sys

import pytest

from pyct.rewrite import condition

# each node kind the rules accept, and the fields they were written for: those they read, and
# those they read nothing from, such as a context, an operator or a constant's kind
WRITTEN_FOR: dict[type[ast.AST], tuple[str, ...]] = {
    ast.Name: ("id", "ctx"),
    ast.Constant: ("value", "kind"),
    ast.Call: ("func", "args", "keywords"),
    ast.keyword: ("arg", "value"),
    # only a method's name and its receiver, as a call's func
    ast.Attribute: ("value", "attr", "ctx"),
    ast.Subscript: ("value", "slice", "ctx"),
    ast.BinOp: ("left", "op", "right"),
    ast.UnaryOp: ("op", "operand"),
    ast.BoolOp: ("op", "values"),
    ast.Compare: ("left", "ops", "comparators"),
    ast.Tuple: ("elts", "ctx"),
    ast.List: ("elts", "ctx"),
    ast.Slice: ("lower", "upper", "step"),
}


@pytest.mark.parametrize("kind", list(WRITTEN_FOR), ids=lambda kind: kind.__name__)
def test_each_kind_the_rules_accept_has_the_fields_they_were_written_for(
    kind: type[ast.AST],
) -> None:
    release = ".".join(str(part) for part in sys.version_info[:2])
    assert kind._fields == WRITTEN_FOR[kind], (
        f"ast.{kind.__name__} has the fields {kind._fields} on Python {release}, where the"
        f" expression rules were written for {WRITTEN_FOR[kind]}: teach"
        " pyct.rewrite.condition's refusal about the new ones, then update this table"
    )


def test_every_kind_whose_parts_the_rules_read_is_pinned() -> None:
    assert set(condition._PLAIN) <= set(WRITTEN_FOR)
