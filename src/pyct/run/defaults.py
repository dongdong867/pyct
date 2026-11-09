"""The constructor parameters a seed leaves out, filled with simple defaults: under ``self``, and
in each object the seed names with ``"__class__"``."""

import inspect
from collections.abc import Mapping
from typing import cast

from pyct.binding.builds import ARGS_KEY, CLASS_KEY, object_forms
from pyct.binding.call import by_position
from pyct.binding.classes import ClassNameError, load_class, signature_of
from pyct.run.target import Target

# the defaults a left-out parameter is filled with, matched by exact type: values bind tracks
_SIMPLE: tuple[type, ...] = (int, float, str, bool)


def with_defaults(target: Target, seed: Mapping[str, object]) -> Mapping[str, object]:
    """The seed with each constructor parameter it leaves out filled, under ``self`` and in
    every object form the call builds (``object_forms``), at any depth.

    A parameter is filled when its default's type is exactly ``int``,
    ``float``, ``str`` or ``bool``, so the default is tracked like a value
    the seed gave and an input's line writes it. It goes after the keys the
    seed gave, in signature order. A parameter an object's ``"__args__"``
    items fill by position is not filled, and any other default is left to
    Python. A constructor Python could not read, or the class of an object
    that does not load, fills nothing at that level; the objects inside it
    still take theirs, and the input reports the class that does not load.
    The caller's seed is never changed.
    """
    name = target.self_name
    forms = object_forms(seed, name)
    fields = None if name is None else forms.args.get(name)
    if target.constructor is not None and type(fields) is dict:
        _fill(cast(dict[str, object], fields), target.constructor, 0)
    for found in forms.found:
        try:
            signature = signature_of(load_class(found.form[CLASS_KEY], target.home))
        except ClassNameError:
            signature = None
        items = found.form.get(ARGS_KEY)
        if signature is not None:
            _fill(found.form, signature, len(items) if type(items) is list else 0)
    return forms.args


def _fill(fields: dict[str, object], signature: inspect.Signature, filled: int) -> None:
    """Fill each simple default ``fields`` leaves out, but those of the first ``filled``
    parameters that take a position."""
    taken = {each.name for each in by_position(signature)[:filled]}
    for parameter in signature.parameters.values():
        left_out = parameter.name not in fields and parameter.name not in taken
        if left_out and type(parameter.default) in _SIMPLE:
            fields[parameter.name] = parameter.default
