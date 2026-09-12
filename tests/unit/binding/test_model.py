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
