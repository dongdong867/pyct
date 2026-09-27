"""The one seed sweep gives an entry, read from its signature with no LLM.

A parameter with no default gets the first of ``VALUES`` that Python's
``isinstance`` accepts for its annotation. ``[]`` and ``{}`` come before
``""`` because ``isinstance`` accepts ``""`` for ``Sequence`` too, and a
``Sequence[str]`` asks for a list first. A parameterized annotation is
tested by its base type, ``Literal`` gives its first value, also as a
member of a union, and ``Annotated[T, ...]`` is read as ``T``. A parameter with no annotation, or
one Python cannot test, gets ``0``.

A default stays in the seed when JSON carries it and ``pyct run``'s own seed
check accepts it. Otherwise the parameter is left out and the target's own
default applies.

A text annotation is read in every module that could have written it, as
the seed check reads it (``binding.resolve``), and those modules must agree
on the value, not on the object: two modules that each define their own
``T`` build two ``list[T]`` objects, and both give ``[]``. Where the value
is agreed, the check the run makes agrees too.
"""

import copy
import inspect
import math
import types
import typing
from collections.abc import Callable

from pyct.binding.annotations import contradictions
from pyct.binding.resolve import checked_annotations, resolved

# the values a parameter with no default is tried with, in order
VALUES: tuple[object, ...] = (0, 0.0, [], {}, "", False, None)

# what JSON carries as it stands, matched by exact type so a subclass is not taken for one
PLAIN = (bool, int, str)

# the parameters a seed never names
GATHERING = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

# no value in VALUES fits, and one Python could not test
NO_FIT = object()
UNTESTABLE = object()


class NoSeedError(Exception):
    """Sweep can give the entry no seed. The message is the reason its row is skipped."""


def seed_of(fn: Callable[..., object]) -> dict[str, object]:
    """The seed for ``fn``, one key per parameter it varies, in signature order."""
    try:
        signature = inspect.signature(fn)
    except Exception as error:
        raise NoSeedError(f"cannot read the signature: {error}") from error
    checks = checked_annotations(signature, fn)
    seed: dict[str, object] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in GATHERING:
            continue
        if parameter.default is inspect.Parameter.empty:
            seed[name] = _value_for(parameter, fn)
        elif carried(parameter.default) and not contradictions(checks, {name: parameter.default}):
            seed[name] = parameter.default
    if not seed:
        raise NoSeedError("no parameter to vary")
    return seed


def carried(value: object) -> bool:
    """Whether seed JSON carries ``value`` as it is: null, a bool, an int, a finite float, a
    str, or a list or a str-keyed dict of such values. A container met twice is not carried."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if item is None or type(item) in PLAIN:
            continue
        if type(item) is float:
            if not math.isfinite(item):
                return False
            continue
        if id(item) in seen or not _container(item):
            return False
        seen.add(id(item))
        pending.extend(item.values() if isinstance(item, dict) else typing.cast(list, item))
    return True


def _container(item: object) -> bool:
    """A list, or a dict whose every key is a str, as JSON writes them."""
    if type(item) is dict:
        return all(type(key) is str for key in item)
    return type(item) is list


def _value_for(parameter: inspect.Parameter, fn: Callable[..., object]) -> object:
    """The value a parameter with no default starts from."""
    if parameter.annotation is inspect.Parameter.empty:
        return 0
    agreed = resolved(parameter.annotation, fn, _typed_fit)
    fit = UNTESTABLE if agreed is None else agreed[1]
    if fit is UNTESTABLE:
        return 0
    if fit is NO_FIT:
        written = inspect.formatannotation(parameter.annotation)
        raise NoSeedError(f"no seed for {parameter.name}: {written}")
    return fit


def _typed_fit(annotation: object) -> tuple[type, object]:
    """``_fit``'s answer beside its type, so modules that agree on ``0`` do not agree on
    ``False`` or ``0.0``, and ``null`` is told from no answer at all."""
    fit = _fit(annotation)
    return (type(fit), fit)


def _fit(annotation: object) -> object:
    """The first of ``VALUES`` the annotation accepts, its ``Literal`` value, ``NO_FIT``, or
    ``UNTESTABLE`` when Python raised testing it.

    A union with a ``Literal`` member gives that member's first value, so
    ``Literal["a", "b"] | None`` gives ``"a"`` rather than a ``null`` that
    leaves nothing to track; a value JSON cannot carry gives way to the rest.
    """
    annotation = _bare(annotation)
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        first = typing.get_args(annotation)[0]
        return first if carried(first) else NO_FIT
    if origin is typing.Union or origin is types.UnionType:
        literal = _literal_in(typing.get_args(annotation))
        if literal is not NO_FIT:
            return literal
    try:
        fits = [value for value in VALUES if _accepts(value, annotation)]
    except Exception:
        return UNTESTABLE
    return copy.copy(fits[0]) if fits else NO_FIT


def _literal_in(members: tuple[object, ...]) -> object:
    """The first value of the first ``Literal`` member JSON carries, or ``NO_FIT``."""
    for member in members:
        if typing.get_origin(_bare(member)) is typing.Literal:
            fit = _fit(member)
            if fit is not NO_FIT:
                return fit
    return NO_FIT


def _bare(annotation: object) -> object:
    """The annotation ``Annotated`` wraps, or the annotation itself."""
    while typing.get_origin(annotation) is typing.Annotated:
        annotation = typing.get_args(annotation)[0]
    return annotation


def _accepts(value: object, annotation: object) -> bool:
    """``isinstance``, reading a union member by member and a parameterized type by its base."""
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        return any(_accepts(value, member) for member in arguments)
    if origin is typing.Annotated:
        return _accepts(value, arguments[0])
    if origin is typing.Literal:
        # a Literal JSON cannot carry, met while the rest of its union is tested
        return any(value == item and type(value) is type(item) for item in arguments)
    if annotation is None:
        return value is None
    return isinstance(value, typing.cast(type, origin or annotation))
