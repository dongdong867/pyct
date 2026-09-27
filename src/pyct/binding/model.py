"""A model the solver answered becomes the next input's arguments."""

from collections.abc import Mapping

from pyct.binding.bind import Noted, Seed, leaf_name
from pyct.binding.shapes import ListAnswer, ListShape, resized
from pyct.binding.walk import Place, Walk


def apply(origin: Seed, model: Mapping[str, object]) -> Seed:
    """The input whose path the solver extends, rebuilt with the model's values, as the next
    input's seed.

    The model names each leaf as ``Seed`` does, with its value, and each tracked list a fork
    read, a row inside one too, with its answer: a new length, and the solver's values at the
    positions a fork read. A value the model does not name keeps what that input had, and so
    does every position of a list no fork read; a position the solver added holds what it
    answered, or starts empty. A leaf name the input does not hold is an error, because the
    solver would be answering about a value that does not exist. The rebuild is the one walk
    of the input an answer costs: it notes the new input's leaves and lists as it goes.
    """
    unknown = [
        name
        for name, value in model.items()
        if name not in origin.leaves and not isinstance(value, ListAnswer)
    ]
    if unknown:
        named = ", ".join(unknown)
        raise ValueError(f"the model names values the input does not hold: {named}")
    applied = _Applied(origin, model)
    args = Walk(applied).rebuilt(origin.args, origin.checks)
    return Seed(args, applied.leaves, applied.shapes(), origin.checks, applied.values)


class _Applied(Noted):
    """The model's visitor: a leaf's answered value, and each answered list at its new length,
    each noted for the new input as ``Seed`` notes them."""

    def __init__(self, origin: Seed, model: Mapping[str, object]) -> None:
        super().__init__()
        self.origin = origin
        self.model = model
        # the shape each list the walk made had in the input, by its copy, so a row inside
        # finds its own
        self.input_shapes: dict[int, ListShape] = {}

    def scalar(self, value: int | float | str, place: Place) -> object:
        # an item of a list is placed with the list's answer already in it
        answered = value if place.in_list else self.model.get(leaf_name(place.access), value)
        return self.noted(answered, place)

    def listed(self, value: list[object], place: Place) -> tuple[list[object], list[object]]:
        name = leaf_name(place.access)
        shape = self._shape(name, place)
        answer = self.model.get(name)
        items = list(value)
        if isinstance(answer, ListAnswer) and shape is not None:
            items = resized(items, answer, shape)
        made, _ = super().listed(items, place)
        if shape is not None:
            self.input_shapes[id(made)] = shape
        return made, items

    def _shape(self, name: str, place: Place) -> ListShape | None:
        """A list's shape: a list the input names on its own, or a row of a list already made."""
        if not place.in_list:
            return self.origin.lists.get(name)
        parent = self.input_shapes.get(id(place.into))
        return None if parent is None else parent.row_at(place.slot)
