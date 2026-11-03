"""A float or a bool value of a tracked dict: read as the target reads it, under a plain key or a
tracked one."""

from typing import Any

import pytest

from pyct.binding.bind import bind
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Downgrade, Expression, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.list_state import plain


@pytest.mark.parametrize(("value", "kind"), [(0.5, ConcolicFloat), (True, ConcolicBool)])
def test_a_value_under_a_plain_key_comes_out_as_its_access(value: object, kind: type) -> None:
    sink: list[SinkItem] = []
    d: Any = bind({"d": {"k": value}}, sink)["d"]

    assert type(d["k"]) is kind
    assert d["k"].expression == ["[]", "d", "'k'"]


@pytest.mark.parametrize(("value", "kind"), [(0.5, ConcolicFloat), (True, ConcolicBool)])
def test_a_value_under_a_tracked_key_comes_out_as_the_target_reads_it(
    value: object, kind: type
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"d": {"k": value}, "name": "k"}, sink)

    read = args["d"][args["name"]]

    wanted: Expression = ["[]", "d", "name"]
    assert type(read) is kind
    assert read.expression == wanted
    assert plain(read) == value


def test_a_value_of_another_type_under_a_tracked_key_comes_out_as_stored() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"d": {"k": None}, "name": "k"}, sink)

    assert args["d"][args["name"]] is None
    assert not [item for item in sink if isinstance(item, Downgrade)]
