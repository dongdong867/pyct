"""The one seed sweep gives an entry, read from its signature with no LLM.

A parameter with no default gets the first of ``VALUES`` that Python's
``isinstance`` accepts for its annotation. ``[]`` and ``{}`` come before
``""`` because ``isinstance`` accepts ``""`` for ``Sequence`` too, and a
``Sequence[str]`` asks for a list first. A parameterized annotation is
tested by its base type, ``Literal`` gives its first value, also as a
member of a union, and ``Annotated[T, ...]`` is read as ``T``. A parameter
with no annotation, or one Python cannot test, gets ``0``.

A default stays in the seed when JSON carries it and ``pyct run``'s own seed
check accepts it. Otherwise the parameter is left out and the target's own
default applies. A dict in a default, at any depth, writes its keys as seed
JSON writes a plain dict's (``binding.seed_keys``). A dict that ``pyct run``
reads as a plain dict, one that no parameter's hint builds into an object,
then reaches the target with the keys it had, ``"__class__"`` among them.

A text annotation is read in every module that could have written it, as
the seed check reads it (``binding.resolve``), and those modules must agree
on the value, not on the object: two modules that each define their own
``T`` build two ``list[T]`` objects, and both give ``[]``. Modules that
agree on what a text asks of a seed agree on its value too, so the value
passes that check.

A parameter with no default whose hint builds a class, as ``pyct run``
reads it (``hint_check``), gets that class's constructor seed instead: the
seed of its constructor's signature by this same rule, ``{}`` for a
constructor that is not Python code or takes no parameter, and an Enum's
first member's value as a one-item list, which ``pyct run`` passes to the
Enum to build. When sweep cannot seed the class, or the class is already
being built on the way down to the parameter, the parameter gets the value
the rule above gives its hint, ``null`` beside None. When that rule gives
none, the entry is skipped with the constructor's reason.

A method a class's own body defines gets the seed of its own parameters.
When Python binds it to an instance read through the class, as ``pyct run``
reads it (``self_class_of``), its first parameter holds the seed of the
class's constructor, ``{}`` for a constructor that is not Python code, from
which each input builds the instance. A method an Enum class binds to a member
is skipped, since ``pyct run`` builds no member as ``self``.
"""

import copy
import enum
import inspect
import json
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.binding.annotations import Builds, Check, contradictions
from pyct.binding.classes import is_a_class
from pyct.binding.hints import hint_check
from pyct.binding.resolve import GATHERING, as_text, checked_annotations, resolved
from pyct.binding.seed_keys import written_key
from pyct.run.target import self_class_of, self_name_of

# the values a parameter with no default is tried with, in order
VALUES: tuple[object, ...] = (0, 0.0, [], {}, "", False, None)

# what JSON carries as it stands, matched by exact type so a subclass is not taken for one; a
# float includes NaN and the infinities, which Python's json writes and pyct run reads
PLAIN = (bool, int, float, str)

# no value in VALUES fits, and one Python could not test
NO_FIT = object()
UNTESTABLE = object()

# a parameter the seed leaves out, and a class the second seed cannot build
LEFT_OUT = object()
NOT_BUILT = object()

# the attributes whose Python code makes a class's constructor Python code
CONSTRUCTORS = ("__init__", "__new__")


class NoSeedError(Exception):
    """Sweep can give the entry no seed. The message is the reason its row is skipped."""


@dataclass(frozen=True)
class _Way:
    """The classes whose constructor seeds are read on the way down to a parameter, outer
    first, and whether this is the second seed, which builds a None default's class."""

    building: tuple[type, ...] = ()
    second: bool = False

    def into(self, cls: type) -> "_Way":
        """The way one class further down. A class already on it needs itself to build."""
        if any(each is cls for each in self.building):
            raise NoSeedError(f"{cls.__qualname__} needs a {cls.__qualname__} to build")
        return _Way((*self.building, cls), self.second)

    def in_second(self) -> "_Way":
        """The same way, read for the second seed."""
        return _Way(self.building, True)


# the way down to a function's own parameters
TOP = _Way()


def first_seed(fn: Callable[..., object]) -> dict[str, object]:
    """The first seed for ``fn``, one key per parameter it varies, in signature order."""
    seed = _seed(fn, TOP.into(fn) if is_a_class(fn) else TOP)
    if not seed:
        raise NoSeedError("no parameter to vary")
    return seed


def seeds_of(fn: Callable[..., object]) -> list[dict[str, object]]:
    """The seeds for ``fn``: ``first_seed``'s, then the second, in which every parameter whose
    default is None, or that has no default and a hint beside None, and whose hint builds a
    class sweep seeds is built from it. One seed when the second's JSON text is the first's."""
    first = first_seed(fn)
    way = TOP.into(fn) if is_a_class(fn) else TOP
    return _pair(first, _seed(fn, way.in_second()))


def _pair(first: dict[str, object], second: dict[str, object]) -> list[dict[str, object]]:
    """The two seeds, or the first alone when the second's JSON text is the same."""
    return [first] if json.dumps(first) == json.dumps(second) else [first, second]


@dataclass(frozen=True)
class Instance:
    """The first and the second seed of the instance a class's methods run on, or why sweep
    cannot seed it."""

    first: dict[str, object] | None = None
    second: dict[str, object] | None = None
    why: str = ""


def instance_of(cls: type) -> Instance:
    """The seeds of the instance ``cls``'s methods run on, read once for all of them."""
    try:
        return Instance(arguments_seed(cls), arguments_seed(cls, TOP.in_second()))
    except NoSeedError as error:
        return Instance(why=str(error))


def method_seeds(cls: type, name: str, instance: Instance | None = None) -> list[dict[str, object]]:
    """The seeds for the method ``cls`` holds under ``name``, as ``seeds_of`` makes a function's,
    with ``instance`` read by ``instance_of(cls)`` when none is given."""
    instance = instance_of(cls) if instance is None else instance
    first = _method_seed(cls, name, instance, TOP)
    return _pair(first, _method_seed(cls, name, instance, TOP.in_second()))


def _method_seed(cls: type, name: str, instance: Instance, way: _Way) -> dict[str, object]:
    method = getattr(cls, name)
    key = None if self_class_of(cls, name, method) is None else self_name_of(_signature(method))
    own = _seed(method, way, skip=key)
    held: dict[str, object] = {}
    if key is not None:
        if issubclass(cls, enum.Enum):
            raise NoSeedError(f"no seed for {key}: pyct run builds no Enum member as self")
        built = instance.second if way.second else instance.first
        if built is None:
            raise NoSeedError(f"no seed for {key}: {instance.why}")
        held[key] = built
    if not own and not any(held.values()):
        raise NoSeedError("no parameter to vary")
    return {**held, **own}


def constructor_seed(cls: type, way: _Way = TOP) -> object:
    """The seed a hint that builds ``cls`` gets: its constructor's seed, ``{}`` for a constructor
    that is not Python code or takes no parameter, or an Enum's first member's value as a
    one-item list."""
    if issubclass(cls, enum.Enum):
        return _member_seed(cls)
    return arguments_seed(cls, way)


def arguments_seed(cls: type, way: _Way = TOP) -> dict[str, object]:
    """The seed of the arguments ``cls``'s constructor takes, ``{}`` for a constructor that is
    not Python code."""
    inner = way.into(cls)
    if not python_constructor(cls):
        return {}
    return _seed(cls, inner)


def _signature(fn: Callable[..., object]) -> inspect.Signature:
    try:
        return inspect.signature(fn)
    except Exception as error:
        raise NoSeedError(f"cannot read the signature: {error}") from error


def _seed(fn: Callable[..., object], way: _Way, skip: str | None = None) -> dict[str, object]:
    """The seed of ``fn``'s parameters, but ``skip``, the one a method's instance goes in."""
    signature = _signature(fn)
    checks = checked_annotations(signature, fn)
    seed: dict[str, object] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in GATHERING or name == skip:
            continue
        value = _parameter_value(parameter, fn, way, checks)
        if value is not LEFT_OUT:
            seed[name] = value
    return seed


def _parameter_value(
    parameter: inspect.Parameter, fn: Callable[..., object], way: _Way, checks: Mapping[str, Check]
) -> object:
    """The value a parameter starts from, or ``LEFT_OUT`` for the target's own default."""
    default = parameter.default
    if default is inspect.Parameter.empty:
        return _value_for(parameter, fn, way)
    if default is None and way.second:
        cls = _built_class(parameter, fn)
        built = NOT_BUILT if cls is None else _built(cls, way)
        if built is not NOT_BUILT:
            return built
    if carried(default) and not contradictions(checks, {parameter.name: default}):
        return _written(default)
    return LEFT_OUT


def _member_seed(cls: type[enum.Enum]) -> list[object]:
    """The Enum's first member's value as a one-item list, which builds that member."""
    first = next(iter(cls.__members__.values()), None)
    if first is None:
        raise NoSeedError(f"{cls.__qualname__} has no member")
    if not carried(first.value):
        raise NoSeedError(f"the first member of {cls.__qualname__} has a value JSON cannot carry")
    return [_written(first.value)]


def python_constructor(cls: type) -> bool:
    """Whether the ``__init__`` or ``__new__`` the class takes is Python code, generated or not."""
    return any(function_of(getattr(cls, name, None)) is not None for name in CONSTRUCTORS)


def function_of(value: object) -> object | None:
    """The Python function ``value`` is, or wraps through ``__wrapped__``, or None.

    A staticmethod or classmethod is read at its function. ``inspect.unwrap``
    raises on a wrapper loop, which is no function either.
    """
    if isinstance(value, staticmethod | classmethod):
        value = value.__func__
    if not callable(value):
        return None
    try:
        target = inspect.unwrap(value)
    except Exception:
        return None
    return target if inspect.isfunction(target) else None


def carried(value: object) -> bool:
    """Whether seed JSON carries ``value``: null, a bool, an int, a float, a str, or a list or a
    str-keyed dict of such values. A container met twice is not carried. A dict's keys are
    written through ``_written``."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if item is None or type(item) in PLAIN:
            continue
        if id(item) in seen or not _container(item):
            return False
        seen.add(id(item))
        pending.extend(item.values() if isinstance(item, dict) else typing.cast(list, item))
    return True


def _written(value: object) -> object:
    """A value ``carried`` accepts, as seed JSON writes it: a copy in which every dict, at any
    depth, writes its keys through ``written_key``, so ``pyct run`` reads a plain dict back with
    the keys it had. The value itself is not changed. A default nested deeper than Python's
    recursion limit raises ``RecursionError``, and the listing gives a failed row that names
    the entry as unread."""
    if type(value) is dict:
        return {written_key(key): _written(item) for key, item in value.items()}
    if type(value) is list:
        return [_written(item) for item in value]
    return value


def _container(item: object) -> bool:
    """A list, or a dict whose every key is a str, as JSON writes them."""
    if type(item) is dict:
        return all(type(key) is str for key in item)
    return type(item) is list


def _value_for(parameter: inspect.Parameter, fn: Callable[..., object], way: _Way) -> object:
    """The value a parameter with no default starts from: its class's constructor seed when its
    hint builds a class, and otherwise, or when sweep cannot seed that class, ``_fitted``'s. A
    hint beside None keeps ``_fitted``'s in the first seed, which the second builds."""
    if parameter.annotation is inspect.Parameter.empty:
        return 0
    cls = _built_class(parameter, fn)
    if cls is None or (not way.second and _beside_none(parameter, fn)):
        return _fitted(parameter, fn, None)
    try:
        return constructor_seed(cls, way)
    except NoSeedError as error:
        return _fitted(parameter, fn, str(error))


def _built_class(parameter: inspect.Parameter, fn: Callable[..., object]) -> type | None:
    """The class the parameter's hint builds, as ``pyct run`` reads it, or None."""
    if parameter.annotation is inspect.Parameter.empty:
        return None
    check = hint_check(parameter.annotation, fn)
    return check.cls if isinstance(check, Builds) else None


def _built(cls: type, way: _Way) -> object:
    """The constructor seed of ``cls``, or ``NOT_BUILT`` when sweep cannot seed it."""
    try:
        return constructor_seed(cls, way)
    except NoSeedError:
        return NOT_BUILT


def _beside_none(parameter: inspect.Parameter, fn: Callable[..., object]) -> bool:
    """Whether the parameter's hint, read where it was written, holds None."""
    return bool(resolved(parameter.annotation, fn, _holds_none))


def _holds_none(annotation: object) -> bool:
    """Whether the annotation is None, or a union with None among its members."""
    annotation = _bare(annotation)
    if annotation is None or annotation is type(None):
        return True
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        return any(_holds_none(member) for member in typing.get_args(annotation))
    return False


def _fitted(parameter: inspect.Parameter, fn: Callable[..., object], why: str | None) -> object:
    """The value ``_fit`` gives the parameter's annotation, read where it was written. When none
    fits, the entry is skipped for ``why``, or with no ``why`` for the annotation as written."""
    agreed = resolved(parameter.annotation, fn, _typed_fit)
    fit = UNTESTABLE if agreed is None else agreed[1]
    if fit is UNTESTABLE:
        return 0
    if fit is NO_FIT:
        shown = inspect.formatannotation(as_text(parameter.annotation)) if why is None else why
        raise NoSeedError(f"no seed for {parameter.name}: {shown}")
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
