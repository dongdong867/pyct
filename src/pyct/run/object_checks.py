"""The checks on one JSON object or list of a seed that a class is built from, at any place in
the seed."""

from __future__ import annotations

import inspect
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pyct.binding.annotations import Builds, Check, NoOneClass, as_typed, contradictions, refused
from pyct.binding.builds import ARGS_KEY, CLASS_KEY, Found, args_problem, object_form
from pyct.binding.call import by_position, call_arguments, positional_only
from pyct.binding.classes import (
    ClassFormError,
    ClassNameError,
    fits_hint,
    hinted_classes,
    load_class,
    signature_of,
    written,
)
from pyct.binding.places import step_in
from pyct.binding.resolve import checked_annotations

# the keys that start and end with __ an object the seed names may hold
_FORM_KEYS = frozenset({CLASS_KEY, ARGS_KEY})


@dataclass(frozen=True)
class ObjectCheck:
    """A class, its constructor's signature as the caller read it or None, and what the
    constructor's annotations ask of the values under their keys: ``checked_annotations``
    less the ``*args`` parameter's."""

    built: type
    signature: inspect.Signature | None
    checks: Mapping[str, Check]

    @classmethod
    def of(cls, owner: type, signature: inspect.Signature | None) -> ObjectCheck:
        """The check for ``owner`` built through ``signature``, which the caller read.

        A ``*args`` parameter's annotation checks no key: a key of that name
        reaches the constructor through ``**kwargs``, or does not fit.
        """
        if signature is None:
            return cls(owner, None, {})
        starred = _star_args(signature)
        checks = checked_annotations(signature, owner)
        return cls(owner, signature, {key: each for key, each in checks.items() if key != starred})

    def lines(
        self,
        place: str,
        value: object,
        allowed: Collection[str] = frozenset(),
        positional: Sequence[object] | None = (),
        built: Collection[int] = frozenset(),
    ) -> list[str]:
        """Every refusal line for the object at ``place``: its shape, its reserved keys, its fit,
        then its values' types.

        A value that is not a JSON object gives that one line. A key that
        starts and ends with ``__`` is refused unless it is ``allowed``, and is
        never bound. The other keys bind as the build passes them, after the
        ``positional`` items; with ``positional`` None, which parameters the
        items fill is unknown, and the fit is not checked. With no signature,
        the fit and the types are not checked. Each ``positional`` item is
        checked against the parameter it fills, then the other values. A value
        in ``built``, an object each input builds, has no type to check
        (``contradictions``).
        """
        if not isinstance(value, dict):
            return [
                f"{place} must be a JSON object of {self._name}'s constructor arguments, got"
                f" {as_typed(value)}"
            ]
        lines = [
            _reserved_line(place, key) for key in value if _reserved(key) and key not in allowed
        ]
        if self.signature is None:
            return lines
        fields = {key: item for key, item in value.items() if not _reserved(key)}
        reason = None if positional is None else fit_failure(self.signature, fields, positional)
        if reason is not None:
            parameters = ", ".join(self.signature.parameters)
            given = _bound_keys(value, positional or ())
            lines.append(f"{place} ({given}) does not fit {self._name}({parameters}): {reason}")
        lines += self._item_lines(step_in(place, ARGS_KEY), positional or (), built)
        return lines + contradictions(self.checks, fields, place, built)

    def list_lines(
        self, place: str, items: Sequence[object], built: Collection[int] = frozenset()
    ) -> list[str]:
        """Every refusal line for the JSON list at ``place``, whose items the class is called
        with by position: its fit, then each item's type, item i named ``place[i]``. With no
        signature, nothing is checked."""
        if self.signature is None:
            return []
        lines: list[str] = []
        reason = fit_failure(self.signature, {}, items)
        if reason is not None:
            parameters = ", ".join(self.signature.parameters)
            count = f"{len(items)} item" if len(items) == 1 else f"{len(items)} items"
            lines.append(f"{place} ({count}) does not fit {self._name}({parameters}): {reason}")
        return lines + self._item_lines(place, items, built)

    def _item_lines(
        self, items_place: str, items: Sequence[object], built: Collection[int]
    ) -> list[str]:
        """The lines for the items passed by position, item i checked against the parameter at
        position i and named ``items_place[i]``. An item past the parameters that take a position
        fills ``*args``, and is not checked."""
        parameters = by_position(cast(inspect.Signature, self.signature))
        return [
            line
            for index, (parameter, item) in enumerate(zip(parameters, items, strict=False))
            if parameter.name in self.checks
            for line in refused(
                self.checks[parameter.name], item, step_in(items_place, index), built
            )
        ]

    @property
    def _name(self) -> str:
        return self.built.__qualname__


def form_lines(found: Found, home: str, built: Collection[int]) -> list[str]:
    """Every refusal line for the object built at ``found.place``: one the seed names, its
    class read as the build reads it, a bare name in the module ``home``, or one its hint
    builds (``_hinted_lines``).

    A ``"__class__"`` that names no class gives its one line: with no class,
    nothing else of the object can be checked. One that names a class its
    hint does not fit (``fits_hint``) gives that line, then the object's lines
    against the class it names. Each object inside this one has lines of its
    own, so a value in ``built`` gives none here.
    """
    if not object_form(found.form):
        return _hinted_lines(found, built)
    form = found.form
    try:
        built_class = load_class(form[CLASS_KEY], home)
    except ClassNameError as error:
        return [_class_line(found.place, error)]
    check = ObjectCheck.of(built_class, signature_of(built_class))
    return _misfit_lines(found, built_class) + _dict_lines(check, found.place, form, built)


def _hinted_lines(found: Found, built: Collection[int]) -> list[str]:
    """Every refusal line for the JSON object or list a hint builds at ``found.place``.

    A hint that names no one class gives its one line, its reason. A list
    takes ``list_lines``, and an object the lines of an object the seed
    names, as its ``"__args__"`` is read the same way.
    """
    hint = found.check
    if isinstance(hint, NoOneClass):
        return [f"{found.place}: {hint.reason}"]
    cls = cast(Builds, hint).cls
    check = ObjectCheck.of(cls, signature_of(cls))
    if isinstance(found.form, list):
        return check.list_lines(found.place, found.form, built)
    return _dict_lines(check, found.place, found.form, built)


def _dict_lines(
    check: ObjectCheck, place: str, form: dict[str, object], built: Collection[int]
) -> list[str]:
    """The lines of a JSON object a class is built from. An ``"__args__"`` that is not a list
    gives its line, then the object's other lines but the fit."""
    problem = args_problem(form)
    if problem is not None:
        rest = check.lines(place, form, _FORM_KEYS, None, built)
        return [f"{step_in(place, ARGS_KEY)} {problem}", *rest]
    items = cast(list[object], form.get(ARGS_KEY, []))
    return check.lines(place, form, _FORM_KEYS, items, built)


def _misfit_lines(found: Found, named: type) -> list[str]:
    """The line for a ``"__class__"`` whose class its place's class hint does not fit, the
    hint written as the classes it names, joined by commas; none when it fits or no class hint
    is there."""
    hint = found.check
    if not isinstance(hint, Builds | NoOneClass) or fits_hint(named, hint):
        return []
    names = [each.__qualname__ for each in hinted_classes(hint)]
    wanted = names[0] if len(names) == 1 else ", ".join(names)
    of = "it" if len(names) == 1 else "one of them"
    given = written(cast(dict[str, object], found.form)[CLASS_KEY])
    place = step_in(found.place, CLASS_KEY)
    return [f"{place} must name {wanted} or a subclass of {of}, got {given}"]


def _class_line(place: str, error: ClassNameError) -> str:
    """The line for a ``"__class__"`` that names no class: what a badly written one must be,
    or why the name reaches no class."""
    written = step_in(place, CLASS_KEY)
    if isinstance(error, ClassFormError):
        return f"{written} {error.problem}"
    return f"{written}: {error.reason}"


def fit_failure(
    signature: inspect.Signature, seed: Mapping[str, object], positional: Sequence[object] = ()
) -> str | None:
    """Why the seed's keys do not bind to ``signature``, as Python's own binding says, or None
    when they bind.

    The ``positional`` items go first by position and fill the first
    parameters. Then each positional-only parameter after those that the seed
    names goes by position, as the call passes it, and the other keys by name
    (``call_arguments`` with ``filled``).
    """
    values, keywords = call_arguments(positional_only(signature), seed, len(positional))
    try:
        signature.bind(*positional, *values, **keywords)
    except TypeError as error:
        return str(error)
    return None


def _star_args(signature: inspect.Signature) -> str | None:
    """The ``*args`` parameter's name, or None for a signature without one."""
    var = inspect.Parameter.VAR_POSITIONAL
    return next((name for name, each in signature.parameters.items() if each.kind is var), None)


def _bound_keys(value: Mapping[str, object], positional: Sequence[object]) -> str:
    """The keys the fit binds, in the seed's order, and ``__args__`` when items are passed by
    position; ``nothing`` for none."""
    bound = [key for key in value if not _reserved(key) or (key == ARGS_KEY and positional)]
    return ", ".join(bound) or "nothing"


def _reserved(key: str) -> bool:
    return key.startswith("__") and key.endswith("__")


def _reserved_line(place: str, key: str) -> str:
    return f"{place} cannot hold {key!r}: pyct reserves keys that start and end with __"
