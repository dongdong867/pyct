"""A model the solver answered becomes the next input's arguments."""

from collections.abc import Mapping

from pyct.binding.bind import Seed, leaf_name, walked


def apply(seed: Seed, model: Mapping[str, object]) -> dict[str, object]:
    """The seed rebuilt, with the model's value at every access it names.

    The model names each value as ``leaves`` does. A value the model does not
    name keeps the seed's: the solver answers only about the leaves, and the
    rest of the input rides along unchanged, in the seed's shape. A name the
    seed does not hold is an error, because the solver would be answering
    about a leaf that does not exist. The rebuild is the one walk of the seed
    an answer costs.
    """
    unknown = [name for name in model if name not in seed.leaves]
    if unknown:
        named = ", ".join(unknown)
        raise ValueError(f"the model names values the seed does not hold: {named}")
    return walked(seed.args, lambda value, access: model.get(leaf_name(access), value))
