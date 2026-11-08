"""A dict under a ``Fields`` check: its values named and tracked, its keys and length kept."""

import json

from pyct.binding.annotations import Fields, Items
from pyct.binding.bind import Seed, bind
from pyct.binding.model import apply
from pyct.core.foundation.branch import SinkItem
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

OWNER = json.dumps(["[]", "self", "'owner'"])
COUNT = json.dumps(["[]", "self", "'count'"])
TAGS = json.dumps(["[]", "self", "'tags'"])
CONFIG = json.dumps(["[]", "self", "'config'"])


def test_the_values_under_fields_are_leaves_and_the_dict_is_not_tracked() -> None:
    seed = Seed.of({"self": {"owner": "ann", "count": 3}, "x": 1}, {"self": Fields({})})

    assert seed.args == {"self": {"owner": "ann", "count": 3}, "x": 1}
    assert type(seed.args["self"]) is dict
    assert seed.leaves == {OWNER: str, COUNT: int, "x": int}
    assert seed.dicts == {}


def test_bind_tracks_the_values_under_fields_in_a_plain_dict() -> None:
    sink: list[SinkItem] = []

    args = bind({"self": {"owner": "ann", "count": 3}}, sink, {"self": Fields({})})

    fields = args["self"]
    assert type(fields) is dict
    assert list(fields) == ["owner", "count"]
    owner, count = fields["owner"], fields["count"]
    assert isinstance(owner, ConcolicStr)
    assert owner.expression == ["[]", "self", "'owner'"]
    assert isinstance(count, ConcolicInt)
    assert count.expression == ["[]", "self", "'count'"]


def test_an_answer_under_fields_comes_back_in_the_seeds_shape() -> None:
    checks = {"self": Fields({})}
    origin = Seed.of({"self": {"owner": "ann", "count": 3}, "x": 1}, checks)

    answered = apply(origin, {OWNER: "admin"})

    assert answered.args == {"self": {"owner": "admin", "count": 3}, "x": 1}
    assert answered.checks == checks
    assert answered.leaves == origin.leaves
    assert answered.dicts == {}


def test_each_field_takes_its_own_check() -> None:
    seed = Seed.of(
        {"self": {"tags": [], "owner": "ann"}}, {"self": Fields({"tags": Items(list, int)})}
    )

    assert seed.lists[TAGS].fill == "int"
    assert seed.leaves == {OWNER: str}


def test_a_dict_one_level_further_in_is_tracked_as_a_dict_inside_a_dict_is() -> None:
    seed = Seed.of({"self": {"config": {"a": 1}}}, {"self": Fields({})})

    assert list(seed.dicts) == [CONFIG]
    assert seed.leaves == {json.dumps(["[]", ["[]", "self", "'config'"], "'a'"]): int}
