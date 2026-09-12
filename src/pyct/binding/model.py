"""A model the solver answered becomes the next input's arguments."""

from collections.abc import Mapping


def apply(seed: Mapping[str, object], model: Mapping[str, object]) -> dict[str, object]:
    """The seed with every key the model names replaced by the model's value.

    A key the model does not name keeps the seed's value: the solver answers
    only about the leaves, and the rest of the input rides along unchanged.
    A key the seed does not have is an error, because the solver would be
    answering about a leaf that does not exist.
    """
    unknown = [name for name in model if name not in seed]
    if unknown:
        named = ", ".join(unknown)
        raise ValueError(f"the model names arguments the seed does not have: {named}")
    return {name: model.get(name, value) for name, value in seed.items()}
