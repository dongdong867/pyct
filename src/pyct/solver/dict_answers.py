"""What cvc5 answered about the dicts of a path, read back into each dict's answer.

A dict's answer is which keys a fork names it holds, how many of the input's other keys it
keeps, and how many keys pyct makes up; a dict the program declared no size for keeps every
other key and makes none up. A value a dict declared for a key the input holds is that input
value's answer, named by its leaf; one for an added key, or for the made-up keys, goes with the
dict's answer (see ``binding.shapes.rekeyed``).
"""

from __future__ import annotations

from collections.abc import Mapping

from pyct.binding.shapes import DictAnswer
from pyct.solver.dict_keys import MADE, MISSING
from pyct.solver.dict_orders import first_keys
from pyct.solver.dicts import DictTerms, Tracked


def dict_answers(terms: DictTerms, model: Mapping[str, object]) -> dict[str, object]:
    """Each dict's answer by the dict's name, and each input value a dict declared by its
    leaf's name."""
    answers: dict[str, object] = {}
    values: dict[str, dict[object, object]] = {name: {} for name in terms.dicts}
    counts = {found.name: _counts(found, model) for found in terms.dicts.values()}
    for constant, (where, key) in terms.valued.items():
        answered = model[constant.strip("|")]
        if key is MISSING:
            answers[where] = answered
        elif key is MADE:
            found = terms.dicts[where]
            for made in found.shape.made_up_keys(
                {*found.shape.keys, *found.named}, counts[where][1]
            ):
                values[where][made] = answered
        else:
            values[where][key] = answered
    for found in terms.dicts.values():
        present = {
            key: bool(model[found.constant(f"in.{j}").strip("|")]) for key, j in found.named.items()
        }
        kept, made = counts[found.name]
        first = first_keys(terms, found, model) if found.order else ()
        answers[found.name] = DictAnswer(present, kept, made, values[found.name], first)
    return answers


def _counts(found: Tracked, model: Mapping[str, object]) -> tuple[int, int]:
    """How many of the input's other keys a dict keeps, and how many keys pyct makes up."""
    if not found.sized:
        return len(found.unnamed), 0
    kept, made = (model[found.constant(part).strip("|")] for part in ("kept", "made"))
    assert isinstance(kept, int) and isinstance(made, int)
    return kept, made
