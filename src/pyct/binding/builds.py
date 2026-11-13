"""The objects each call builds before it calls the target, and the plan of that call.

An object form is a JSON object holding ``"__class__"``. One is built at a
parameter's own value, as a keyword value or an ``"__args__"`` item of
another object form, as a value directly under the fields of the instance a
method runs on, and inside a plain list or dict at any of those places, at
any depth. The dict under ``self`` itself is no object form: its class is
the method's. In any other place such a dict stays a dict.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard, cast

from pyct.binding.annotations import Builds, Check, Fields, Items, NoOneClass, item_check
from pyct.binding.call import call_arguments, positional_only
from pyct.binding.classes import ClassNameError, load_class, signature_of, written
from pyct.binding.hints import NOTHING, Inside, inside_of
from pyct.binding.places import step_in
from pyct.binding.seed_keys import ARGS_KEY, CLASS_KEY

# where a value sits in the seed as the traversal copies it, the place it is written at, and
# what its hint asks
type _Holder = dict[Any, object] | list[object]
type _Spot = tuple[object, _Holder, Any, str, Check | None]

# whether a value is an object form, given what the hint at its place asks
type FormTest = Callable[[object, Check | None], bool]


def object_form(value: object) -> TypeGuard[dict[str, object]]:
    """Whether ``value`` is an object form: exactly a ``dict``, holding ``"__class__"``.

    Whether one is built depends on its place too: the walk and the plan of a call each say
    where they look for one.
    """
    return type(value) is dict and CLASS_KEY in value


def hinted(value: object, check: Check | None) -> TypeGuard[dict[str, object] | list[object]]:
    """Whether a class hint builds ``value``: exactly a ``dict`` or a ``list``, under a hint that
    names a class or names no one class. A dict holding ``"__class__"`` builds the class it
    names, and every other value passes as it is."""
    return isinstance(check, Builds | NoOneClass) and (type(value) is dict or type(value) is list)


def seed_form(value: object, check: Check | None) -> bool:
    """Whether a value of seed JSON is an object form, where a call builds one: a dict holding
    ``"__class__"`` (``object_form``), or a dict or list a class hint builds (``hinted``)."""
    return object_form(value) or hinted(value, check)


@dataclass(frozen=True)
class Bound:
    """A call's arguments as ``bind`` made them, and each copy its walk made as an object form,
    by identity: a dict it read as one, or a dict or list a class hint builds.

    By then a plain dict's ``"!__class__"`` reads ``"__class__"``, so the plan of the call
    builds these and no other (``is_form``).
    """

    args: dict[str, object]
    forms: Mapping[int, object]

    def is_form(self, value: object, _check: Check | None) -> bool:
        """Whether the walk copied ``value`` as an object form."""
        return id(value) in self.forms and self.forms[id(value)] is value


def hinted_items(value: object, check: Check | None) -> TypeGuard[list[object] | dict[Any, object]]:
    """Whether a class hint fixes the shape of ``value``: exactly a ``list`` under a ``list[C]``
    hint, or exactly a ``dict`` under a ``dict[str, C]`` hint, at any level (a fixed ``Items``).
    Such a list keeps its length and such a dict its keys, and each value in it takes the
    fixed ``Items``' ``each``: ``C``, or the fixed list or dict hint inside, as of
    ``list[list[C]]``. The walk, the traversal, the defaults and the plan read this one test."""
    return isinstance(check, Items) and check.fixed and type(value) is check.kind


def form_class(form: object, check: Check | None, home: str) -> type:
    """The class an object form builds: the one its ``"__class__"`` names, read in ``home``, or
    else its hint's. A class that does not load, or a hint that names no one class, is a
    ``ClassNameError`` with the reason."""
    if object_form(form):
        return load_class(form[CLASS_KEY], home)
    if isinstance(check, NoOneClass):
        raise ClassNameError(check.reason)
    return cast(Builds, check).cls


def inside(form: object, check: Check | None, home: str | None) -> Inside:
    """What the values inside an object form ask: its class's constructor hints (``inside_of``).

    The one rule the walk, the traversal, the defaults and the plan read.
    A form whose class does not load asks nothing, and with no ``home`` a
    form that names its class asks nothing either: its class is not looked
    up.
    """
    if home is None and object_form(form):
        return NOTHING
    try:
        return inside_of(form_class(form, check, home or ""))
    except ClassNameError:
        return NOTHING


def holding_forms(args: Mapping[str, object], is_form: FormTest = seed_form) -> set[int]:
    """The lists and dicts in ``args`` that hold an object form at any depth, by identity, each
    form one ``is_form`` names with no hint asked.

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
        if is_form(value, None):
            forms.append(id(value))
        pending.extend((item, id(value)) for item in _held(value, is_form))
    return _reaching(forms, above)


def _held(
    value: list[object] | dict[object, object], is_form: FormTest = seed_form
) -> Iterable[object]:
    """The values a list or dict holds where a form is looked for: every one, but a form's
    ``"__class__"``."""
    if type(value) is list:
        return value
    items = cast(dict[object, object], value)
    if is_form(items, None):
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
    """An object form at its place, as ``object_forms`` copied it, the list or dict and slot
    its copy sits in, and what the hint at its place asks."""

    place: str
    form: dict[str, object] | list[object]
    into: _Holder
    slot: Any
    check: Check | None = None

    @property
    def spot(self) -> tuple[_Holder, Any]:
        """The list or dict its object goes into, and the slot, when no arguments hold it."""
        return self.into, self.slot


@dataclass(frozen=True)
class Forms:
    """A seed with each container on the way to an object form copied, and the forms in
    it, innermost first."""

    args: dict[str, object]
    found: tuple[Found, ...]

    def outer_first(self) -> list[Found]:
        """The forms in seed order, each before the forms inside it, depth first: the order a
        person reads the seed in. A list or dict is gone into once, by a loop."""
        by_identity = {id(found.form): found for found in self.found}
        ordered: list[Found] = []
        seen: set[int] = set()
        pending: list[object] = list(reversed(self.args.values()))
        while pending:
            value = pending.pop()
            if (type(value) is not list and type(value) is not dict) or id(value) in seen:
                continue
            seen.add(id(value))
            if id(value) in by_identity:
                ordered.append(by_identity[id(value)])
            pending.extend(reversed(list(_held(cast(list[object] | dict[object, object], value)))))
        return ordered


def object_forms(
    args: Mapping[str, object],
    self_name: str | None,
    checks: Mapping[str, Check] | None = None,
    home: str | None = None,
    is_form: FormTest = seed_form,
) -> Forms:
    """Each object form ``args`` holds, with its place, innermost first.

    The objects inside one come before it, siblings in seed order, depth
    first. ``self_name`` is the parameter whose dict holds the fields of the
    instance a method runs on. Every dict and list on the way to a form is
    copied (``holding_forms``), the form too, so the caller's seed never
    changes. So are the dict under ``self_name`` and each form's
    ``"__args__"`` list, whatever they hold. A form, or a list or dict on the
    way to one, is gone into once: one reached again, at a second place or
    inside itself, stays as it came there. The traversal is a loop, not a
    call per level.

    With ``checks``, what each parameter's hint asks, a dict a class hint
    builds is a form too (``hinted``), and each value in a form takes its
    constructor's hint (``inside``), a bare class name read in ``home``. A
    list or dict under a ``list[C]`` or ``dict[str, C]`` hint is gone into
    and copied too (``hinted_items``), and each list or dict gone into gives
    each value in it what its hint asks of its items.

    ``is_form`` says which values are forms: by default those of seed JSON
    (``seed_form``), and in a call the ones bind's walk copied as forms
    (``Bound``).
    """
    holding = holding_forms(args, is_form)
    top = dict(args)
    pending = _parameters(top, self_name, checks or {})
    found: list[Found] = []
    seen: set[int] = set()
    # the last pushed goes first, so the forms come out right to left, outer before inner
    while pending:
        value, holder, slot, place, check = pending.pop()
        form = is_form(value, check)
        if not (form or id(value) in holding or hinted_items(value, check)) or id(value) in seen:
            continue
        seen.add(id(value))
        if form:
            copied = holder[slot] = _copy(cast(dict[str, object] | list[object], value))
            found.append(Found(place, copied, holder, slot, check))
            pending.extend(_inside(copied, place, inside(copied, check, home)))
        else:
            pending.extend(_copied(value, holder, slot, place, check))
    return Forms(top, tuple(reversed(found)))


def _parameters(
    top: dict[str, object], self_name: str | None, checks: Mapping[str, Check]
) -> list[_Spot]:
    """Where the traversal starts: each parameter's value, or each value under the fields of
    the instance a method runs on, in a copy of that dict."""
    pending: list[_Spot] = []
    for name, value in top.items():
        check = checks.get(name)
        if name == self_name and type(value) is dict:
            fields = top[name] = dict(value)
            each = check.each if isinstance(check, Fields) else {}
            pending.extend(
                (item, fields, key, step_in(name, key), each.get(key))
                for key, item in fields.items()
            )
        else:
            pending.append((value, top, name, name, check))
    return pending


def _copied(
    value: object, holder: _Holder, slot: Any, place: str, ask: Check | None
) -> Iterator[_Spot]:
    """A list or dict on the way to a form, copied into its slot, and the values in it, each
    with what ``ask`` asks of it (``item_check``)."""
    if type(value) is list:
        items = holder[slot] = list(cast(list[object], value))
        return (
            (each, items, at, step_in(place, at), item_check(ask, list, at))
            for at, each in enumerate(items)
        )
    copied = holder[slot] = dict(cast(dict[Any, object], value))
    return (
        (each, copied, key, step_in(place, key), item_check(ask, dict, key))
        for key, each in list(copied.items())
    )


def _copy(form: dict[str, object] | list[object]) -> dict[str, object] | list[object]:
    return dict(form) if type(form) is dict else list(form)


def _inside(form: dict[str, object] | list[object], place: str, ask: Inside) -> Iterator[_Spot]:
    """The values inside an object form where another can be built: a list's items, its
    ``"__args__"`` items, in a copy of that list, and every other value but ``"__class__"``,
    each with its constructor parameter's hint."""
    if isinstance(form, list):
        yield from (
            (each, form, at, step_in(place, at), ask.items.each.get(at))
            for at, each in enumerate(form)
        )
        return
    for key, item in list(form.items()):
        if key == CLASS_KEY:
            continue
        if key == ARGS_KEY and type(item) is list:
            yield from _copied(item, form, key, step_in(place, key), ask.items)
        else:
            yield item, form, key, step_in(place, key), ask.keys.each.get(key)


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

    Each build's object goes into a slot of a later build's arguments, of the call's, or of
    a list or dict among them, so the plan holds the only references pyct keeps to them.
    """

    builds: list[Build]
    positional: list[object]
    keywords: dict[str, object]

    def drop(self) -> None:
        """Let go of every object the plan holds, and leave the lists and dicts the target
        was given as they are."""
        for build in self.builds:
            build.positional.clear()
            build.keywords.clear()
        self.builds.clear()
        self.positional.clear()
        self.keywords.clear()


def plan_call(
    args: Mapping[str, object] | Bound,
    positional: Sequence[inspect.Parameter],
    self_build: SelfBuild | None,
    home: str,
    checks: Mapping[str, Check] | None = None,
) -> CallPlan:
    """How one call builds each object form ``args`` holds, and calls the target.

    ``positional`` is the target's parameters passed by position, a bare
    class name is read in the module ``home``, and ``checks`` says which
    values a class hint builds (``object_forms``). With ``self_build`` and a dict
    under its name, the instance a method runs on is the last build, and goes
    first in the call. Each object passes its ``"__args__"`` items by
    position, then its positional-only parameters, then its other keys by
    name. Every class loads before any build is planned, so the first object,
    innermost first, whose class does not load or whose ``"__args__"`` is not
    a list, or whose hint names no one class, is the ``BuildError``.

    ``args`` is seed JSON, whose forms its keys and hints say, or what ``bind``
    made of it, whose forms are the ones its walk copied as forms (``Bound``).
    """
    values, is_form = (args.args, args.is_form) if isinstance(args, Bound) else (args, seed_form)
    if self_build is not None and type(values.get(self_build.name)) is not dict:
        self_build = None
    self_name = None if self_build is None else self_build.name
    forms = object_forms(values, self_name, checks, home, is_form)
    loaded = [(found, _class_of(found, home)) for found in forms.found]
    calls = {id(found.form): _arguments(found.form, cls) for found, cls in loaded}
    call, last = _target_call(forms.args, positional, self_build)
    lasts = () if last is None else (last,)
    holders = _holders(calls, [call, *calls.values(), *((b.positional, b.keywords) for b in lasts)])
    builds = [
        Build(cls, found.place, *calls[id(found.form)], *holders.get(id(found.form), found.spot))
        for found, cls in loaded
    ]
    return CallPlan([*builds, *lasts], *call)


def _class_of(found: Found, home: str) -> type:
    """The class an object form builds, once its ``"__args__"`` is known to be a list."""
    try:
        cls = form_class(found.form, found.check, home)
    except ClassNameError as error:
        raise BuildError(found.place, error.reason) from error
    problem = None if isinstance(found.form, list) else args_problem(found.form)
    if problem is not None:
        raise BuildError(found.place, f"'{ARGS_KEY}' {problem}")
    return cls


def args_problem(form: Mapping[str, object]) -> str | None:
    """What an object form's ``"__args__"`` must be when it is not a list, or None when it is
    one or the form has none."""
    items = form.get(ARGS_KEY, [])
    return None if type(items) is list else f"must be a list, got {written(items)}"


def _arguments(
    form: dict[str, object] | list[object], cls: type
) -> tuple[list[object], dict[str, object]]:
    """What an object form's class is called with: a list's items by position, or its
    ``"__args__"`` items, then its positional-only parameters by position, as
    ``call_arguments`` passes them after those items, and every other key by name."""
    if isinstance(form, list):
        return list(form), {}
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
    """Where each object form's object goes, by the form's identity, when a list or dict of
    arguments holds the form: that list or dict, and its slot there. A form inside a plain
    list or dict keeps the slot the traversal copied it into."""
    holders: dict[int, tuple[_Holder, Any]] = {}
    for values, keywords in arguments:
        for at, value in enumerate(values):
            if id(value) in calls:
                holders[id(value)] = (values, at)
        for key, value in keywords.items():
            if id(value) in calls:
                holders[id(value)] = (keywords, key)
    return holders
