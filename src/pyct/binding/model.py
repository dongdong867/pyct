"""A model the solver answered becomes the next input's arguments."""

from collections.abc import Mapping

from pyct.binding.bind import leaf_name, leaves, walked


def apply(seed: Mapping[str, object], model: Mapping[str, object]) -> dict[str, object]:
    """The seed rebuilt, with the model's value at every access it names.

    The model names each value as ``leaves`` does. A value the model does not
    name keeps the seed's: the solver answers only about the leaves, and the
    rest of the input rides along unchanged, in the seed's shape. A name the
    seed does not hold is an error, because the solver would be answering
    about a leaf that does not exist.
    """
    held = leaves(seed)
    unknown = [name for name in model if name not in held]
    if unknown:
        named = ", ".join(unknown)
        raise ValueError(f"the model names values the seed does not hold: {named}")
    return walked(seed, lambda value, access: model.get(leaf_name(access), value))
