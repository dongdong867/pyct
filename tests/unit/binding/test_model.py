import json

import pytest

from pyct.binding.annotations import Items
from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.binding.shapes import ArrayValue, ListAnswer, ListShape


def test_the_model_replaces_the_keys_it_names_and_leaves_the_rest() -> None:
    assert apply(Seed.of({"x": 3, "y": 7}), {"x": 12}).args == {"x": 12, "y": 7}


def test_an_empty_model_gives_back_the_seed() -> None:
    seed: dict[str, object] = {"x": 3}

    args = apply(Seed.of(seed), {}).args

    assert args == {"x": 3}
    assert args is not seed


def test_applying_a_model_leaves_the_seed_alone() -> None:
    seed: dict[str, object] = {"x": 3}

    apply(Seed.of(seed), {"x": 12})

    assert seed == {"x": 3}


def test_a_model_about_a_key_the_seed_does_not_have_is_an_error() -> None:
    # the solver answered about a leaf that does not exist; the name says which
    with pytest.raises(ValueError, match="z"):
        apply(Seed.of({"x": 3}), {"z": 12})


def test_the_model_writes_a_value_inside_at_its_access() -> None:
    seed: dict[str, object] = {"config": {"server": {"port": 1, "host": "x"}}, "items": [1, 2]}
    port = json.dumps(["[]", ["[]", "config", "'server'"], "'port'"])
    # an item of a list comes back as the list's answer: its length, and the position read
    items = ListAnswer(length=2, arrays={"int": ArrayValue(0, {1: -60})}, read=frozenset({1}))

    args = apply(Seed.of(seed), {port: 70000, "items": items}).args

    assert args == {"config": {"server": {"port": 70000, "host": "x"}}, "items": [1, -60]}
    assert seed == {"config": {"server": {"port": 1, "host": "x"}}, "items": [1, 2]}


def test_a_model_about_an_access_the_seed_does_not_have_is_an_error() -> None:
    with pytest.raises(ValueError, match="items"):
        apply(Seed.of({"items": [1]}), {json.dumps(["[]", "items", 1]): 5})


def test_the_model_keeps_a_list_that_holds_itself_one_list() -> None:
    xs: list[object] = [0]
    xs.append(xs)

    answer = ListAnswer(length=2, arrays={"int": ArrayValue(0, {0: 7})}, read=frozenset({0}))

    args = apply(Seed.of({"xs": xs}), {"xs": answer}).args

    copy = args["xs"]
    assert isinstance(copy, list)
    assert copy[0] == 7
    assert copy[1] is copy
    assert xs[0] == 0


def test_a_seed_holds_the_leaves_bind_tracks_in_it() -> None:
    seed = Seed.of({"items": [1, "a"], "config": {"k": 2}, "flag": True})

    # an item of a tracked list is the list's; a value in a dict is a leaf of its own
    assert seed.leaves == {json.dumps(["[]", "config", "'k'"]): int}
    assert seed.lists == {"items": ListShape(kinds=("int", "str"), fill="none")}


def test_a_list_keeps_every_item_no_fork_read_and_grows_by_its_kind() -> None:
    seed = Seed.of({"items": [1, 2]})
    answer = ListAnswer(length=4, arrays={"int": ArrayValue(9, {3: 101})}, read=frozenset({3}))

    args = apply(seed, {"items": answer}).args

    # the two items no fork read keep what the input had, and the added ones are ints
    assert args == {"items": [1, 2, 9, 101]}


def test_a_list_shortens_from_its_end() -> None:
    answer = ListAnswer(length=1, arrays={"int": ArrayValue(5, {})}, read=frozenset())

    assert apply(Seed.of({"items": [7, 8, 9]}), {"items": answer}).args == {"items": [7]}


def test_an_added_item_takes_the_annotation_when_the_items_do_not_say() -> None:
    seed = Seed.of({"items": [], "names": []}, {"names": Items(list, str)})
    grown = ListAnswer(length=1)

    args = apply(seed, {"items": grown, "names": grown}).args

    assert args == {"items": [None], "names": [""]}


def test_a_list_inside_a_list_grows_and_an_added_one_starts_empty() -> None:
    seed = Seed.of({"grid": [[]]}, {"grid": Items(list, Items(list, int))})
    row = json.dumps(["[]", "grid", 0])
    rows = {
        "grid": ListAnswer(length=2),
        row: ListAnswer(length=1, arrays={"int": ArrayValue(0, {0: 6})}, read=frozenset({0})),
    }

    assert apply(seed, rows).args == {"grid": [[6], []]}
    assert seed.lists["grid"].rows[0].fill == "int"
