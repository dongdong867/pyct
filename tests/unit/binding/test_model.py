import json

import pytest

from pyct.binding.model import apply


def test_the_model_replaces_the_keys_it_names_and_leaves_the_rest() -> None:
    assert apply({"x": 3, "y": 7}, {"x": 12}) == {"x": 12, "y": 7}


def test_an_empty_model_gives_back_the_seed() -> None:
    seed: dict[str, object] = {"x": 3}

    args = apply(seed, {})

    assert args == {"x": 3}
    assert args is not seed


def test_applying_a_model_leaves_the_seed_alone() -> None:
    seed: dict[str, object] = {"x": 3}

    apply(seed, {"x": 12})

    assert seed == {"x": 3}


def test_a_model_about_a_key_the_seed_does_not_have_is_an_error() -> None:
    # the solver answered about a leaf that does not exist; the name says which
    with pytest.raises(ValueError, match="z"):
        apply({"x": 3}, {"z": 12})


def test_the_model_writes_a_value_inside_at_its_access() -> None:
    seed: dict[str, object] = {"config": {"server": {"port": 1, "host": "x"}}, "items": [1, 2]}
    port = json.dumps(["[]", ["[]", "config", "'server'"], "'port'"])
    second = json.dumps(["[]", "items", 1])

    args = apply(seed, {port: 70000, second: -60})

    assert args == {"config": {"server": {"port": 70000, "host": "x"}}, "items": [1, -60]}
    assert seed == {"config": {"server": {"port": 1, "host": "x"}}, "items": [1, 2]}


def test_a_model_about_an_access_the_seed_does_not_have_is_an_error() -> None:
    with pytest.raises(ValueError, match="items"):
        apply({"items": [1]}, {json.dumps(["[]", "items", 1]): 5})


def test_the_model_keeps_a_list_that_holds_itself_one_list() -> None:
    xs: list[object] = [0]
    xs.append(xs)

    args = apply({"xs": xs}, {json.dumps(["[]", "xs", 0]): 7})

    copy = args["xs"]
    assert isinstance(copy, list)
    assert copy[0] == 7
    assert copy[1] is copy
    assert xs[0] == 0
