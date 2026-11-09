"""The objects each call builds before it calls the target, and the plan of that call.

An object form is a JSON object holding ``"__class__"``. One is built at a
parameter's own value, as a keyword value or an ``"__args__"`` item of
another object form, and as a value directly under the fields of the
instance a method runs on. The dict under ``self`` itself is no object form:
its class is the method's. In any other place such a dict stays a dict.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard, cast

from pyct.binding.call import call_arguments, positional_only
from pyct.binding.classes import ClassNameError, load_class, signature_of, written
from pyct.binding.places import step_in

# the key that names an object form's class, and the key of the items it passes by position
CLASS_KEY = "__class__"
ARGS_KEY = "__args__"

# where a value sits in the seed as the traversal copies it, and the place it is written at
type _Holder = dict[str, object] | list[object]
type _Spot = tuple[object, _Holder, Any, str]


def object_form(value: object) -> TypeGuard[dict[str, object]]:
    """Whether ``value`` is an object form: exactly a ``dict``, holding ``"__class__"``.

    Whether one is built depends on its place too: the walk and the plan of a call each say
    where they look for one.
    """
    return type(value) is dict and CLASS_KEY in value


def holding_forms(args: Mapping[str, object]) -> set[int]:
    """The lists and dicts in ``args`` that hold an object form at any depth, by identity.

    A form is held along plain lists, plain dicts and other forms, from each
    parameter's value down: exactly a ``list`` or a ``dict``, never a tuple,
    a subclass or any other object. Each is gone into once, by a loop, and
    every one that reaches a form is listed, whichever path reached it
    first, so a list in a cycle is listed when anything in the cycle holds a
    form.
    """
    above: dict[int, list[int]] = {}
    forms: list[int] = []
    pending: list[tuple[object, int | None]] = [(value, None) for value in args.values()]
    while pending:
        value, parent = pending.pop()
        if type(value) is not list and type(value) is not dict:
            continue
        known = id(value) in above
        parents = above.setdefault(id(value), [])
        if parent is not None:
            parents.append(parent)
        if known:
            continue
        if object_form(value):
            forms.append(id(value))
        pending.extend((item, id(value)) for item in _held(value))
    return _reaching(forms, above)


def _held(value: list[object] | dict[object, object]) -> Iterable[object]:
    """The values a list or dict holds where a form is looked for: every one, but a form's
    ``"__class__"``."""
    if type(value) is list:
        return value
    items = cast(dict[object, object], value)
    if object_form(items):
        return (item for key, item in items.items() if key != CLASS_KEY)
    return items.values()


def _reaching(forms: list[int], above: Mapping[int, list[int]]) -> set[int]:
    """Every container some path of ``above`` leads up to from a form."""
    reaching: set[int] = set()
    stack = list(forms)
    while stack:
        for parent in above[stack.pop()]:
            if parent not in reaching:
                reaching.add(parent)
                stack.append(parent)
    return reaching


@dataclass(frozen=True)
class SelfBuild:
    """How each call builds the instance a method runs on.

    ``cls`` is the class the target's spec names before the method, and
    ``name`` the method's first parameter, the seed's key for the
    constructor's arguments. ``positional`` is the constructor's parameters
    each construction passes by position, read once at load.
    """

    cls: type
    name: str
    positional: tuple[inspect.Parameter, ...] = ()


@dataclass(frozen=True)
class Found:
    """An object form at its place, as ``object_forms`` copied it."""

    place: str
    form: dict[str, object]


@dataclass(frozen=True)
class Forms:
    """A seed with each container on the way to an object form copied, and the forms in
    it, innermost first."""

    args: dict[str, object]
    found: tuple[Found, ...]


def object_forms(args: Mapping[str, object], self_name: str | None) -> Forms:
    """Each object form ``args`` holds, with its place, innermost first.

    The objects inside one come before it, siblings in seed order, depth
    first. ``self_name`` is the parameter whose dict holds the fields of the
    instance a method runs on. Every dict and list on the way to a form is
    copied, the form too, so the caller's seed never changes. A form is
    listed once: one reached again, at a second place or inside itself, stays
    as it came there. The traversal is a loop, not a call per level.
    """
    top = dict(args)
    pending: list[_Spot] = []
    for name, value in top.items():
        if name == self_name and type(value) is dict:
            fields = top[name] = dict(value)
            pending.extend((item, fields, key, step_in(name, key)) for key, item in fields.items())
        else:
            pending.append((value, top, name, name))
    found: list[Found] = []
    seen: set[int] = set()
    # the last pushed goes first, so the forms come out right to left, outer before inner
    while pending:
        value, holder, slot, place = pending.pop()
        if not object_form(value) or id(value) in seen:
            continue
        seen.add(id(value))
        form = holder[slot] = dict(value)
        found.append(Found(place, form))
        pending.extend(_inside(form, place))
    return Forms(top, tuple(reversed(found)))


def _inside(form: dict[str, object], place: str) -> Iterator[_Spot]:
    """The values inside an object form where another can be built: its ``"__args__"`` items,
    in a copy of that list, and every other value but ``"__class__"``."""
    for key, item in list(form.items()):
        if key == CLASS_KEY:
            continue
        if key == ARGS_KEY and type(item) is list:
            items: list[object] = list(item)
            form[key] = items
            at = step_in(place, key)
            yield from ((each, items, i, step_in(at, i)) for i, each in enumerate(items))
        else:
            yield item, form, key, step_in(place, key)


class BuildError(Exception):
    """An object a call cannot build: its ``place`` in the seed, and the ``reason``."""

    def __init__(self, place: str, reason: str) -> None:
        super().__init__(f"{place}: {reason}")
        self.place = place
        self.reason = reason


@dataclass(frozen=True)
class Build:
    """One object a call builds: its class, its place, the arguments it is called with, and
    the list or dict and slot its object goes into."""

    cls: type
    place: str
    positional: list[object]
    keywords: dict[str, object]
    into: _Holder
    slot: Any


@dataclass(frozen=True)
class CallPlan:
    """One call: each object to build, innermost first, then the target's own arguments.

    Each build's object goes into a slot of a later build's arguments or of the call's, so
    the plan holds the only references pyct keeps to them.
    """

    builds: tuple[Build, ...]
    positional: list[object]
    keywords: dict[str, object]

    def drop(self) -> None:
        """Let go of every object the plan holds."""
        for build in self.builds:
            build.positional.clear()
            build.keywords.clear()
        self.positional.clear()
        self.keywords.clear()


def plan_call(
    args: Mapping[str, object],
    positional: Sequence[inspect.Parameter],
    self_build: SelfBuild | None,
    home: str,
) -> CallPlan:
    """How one call builds each object form ``args`` holds, and calls the target.

    ``positional`` is the target's parameters passed by position, and a bare
    class name is read in the module ``home``. With ``self_build`` and a dict
    under its name, the instance a method runs on is the last build, and goes
    first in the call. Each object passes its ``"__args__"`` items by
    position, then its positional-only parameters, then its other keys by
    name. Every class loads before any build is planned, so the first object,
    innermost first, whose class does not load or whose ``"__args__"`` is not
    a list is the ``BuildError``.
    """
    if self_build is not None and type(args.get(self_build.name)) is not dict:
        self_build = None
    forms = object_forms(args, None if self_build is None else self_build.name)
    loaded = [(found, _class_of(found, home)) for found in forms.found]
    calls = {id(found.form): _arguments(found.form, cls) for found, cls in loaded}
    call, last = _target_call(forms.args, positional, self_build)
    lasts = () if last is None else (last,)
    holders = _holders(calls, [call, *calls.values(), *((b.positional, b.keywords) for b in lasts)])
    builds = tuple(
        Build(cls, found.place, *calls[id(found.form)], *holders[id(found.form)])
        for found, cls in loaded
    )
    return CallPlan((*builds, *lasts), *call)


def _class_of(found: Found, home: str) -> type:
    """The class an object form names, once its ``"__args__"`` is known to be a list."""
    try:
        cls = load_class(found.form[CLASS_KEY], home)
    except ClassNameError as error:
        raise BuildError(found.place, error.reason) from error
    items = found.form.get(ARGS_KEY, [])
    if type(items) is not list:
        raise BuildError(found.place, f"'{ARGS_KEY}' must be a list, got {written(items)}")
    return cls


def _arguments(form: dict[str, object], cls: type) -> tuple[list[object], dict[str, object]]:
    """What an object form's class is called with: its ``"__args__"`` items, then its
    positional-only parameters by position, as ``call_arguments`` passes them after those
    items, and every other key by name."""
    items = cast(list[object], form.get(ARGS_KEY, []))
    keys = {key: value for key, value in form.items() if key not in (CLASS_KEY, ARGS_KEY)}
    signature = signature_of(cls)
    parameters = () if signature is None else positional_only(signature)
    values, keywords = call_arguments(parameters, keys, len(items))
    return [*items, *values], keywords


def _target_call(
    args: Mapping[str, object],
    positional: Sequence[inspect.Parameter],
    self_build: SelfBuild | None,
) -> tuple[tuple[list[object], dict[str, object]], Build | None]:
    """The target's own arguments, and the build of the instance a method runs on, whose
    object takes the first position."""
    if self_build is None:
        values, keywords = call_arguments(positional, args)
        return (list(values), keywords), None
    name = self_build.name
    rest = {key: value for key, value in args.items() if key != name}
    after = [parameter for parameter in positional if parameter.name != name]
    values, keywords = call_arguments(after, rest)
    call: tuple[list[object], dict[str, object]] = ([None, *values], keywords)
    own, by_name = call_arguments(self_build.positional, cast(dict[str, object], args[name]))
    return call, Build(self_build.cls, name, list(own), by_name, call[0], 0)


def _holders(
    calls: Mapping[int, object], arguments: Iterable[tuple[list[object], dict[str, object]]]
) -> dict[int, tuple[_Holder, Any]]:
    """Where each object form's object goes, by the form's identity: the list or dict of
    arguments that holds the form, and its slot there."""
    holders: dict[int, tuple[_Holder, Any]] = {}
    for values, keywords in arguments:
        for at, value in enumerate(values):
            if id(value) in calls:
                holders[id(value)] = (values, at)
        for key, value in keywords.items():
            if id(value) in calls:
                holders[id(value)] = (keywords, key)
    return holders
