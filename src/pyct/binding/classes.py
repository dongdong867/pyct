"""A class a seed names with ``"__class__"``, and its constructor's signature.

The text is ``MODULE::QUALNAME``, as a target is written, or a bare
``QUALNAME``, read in the home module: the module the target function was
written in. QUALNAME is one or more names joined by dots, each read once
with ``getattr``.
"""

from __future__ import annotations

import importlib
import inspect
from typing import TypeGuard

from pyct.binding.annotations import Builds, NoOneClass, as_typed

# the types a JSON value is read as
_JSON_TYPES: frozenset[type] = frozenset({dict, list, str, int, float, bool, type(None)})

# each class's signature, or None for one Python cannot read, by the class's identity; the
# class is kept beside it, so its identity is not reused
_SIGNATURES: dict[int, tuple[type, inspect.Signature | None]] = {}


class ClassNameError(Exception):
    """A ``"__class__"`` value that names no class, and ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ClassFormError(ClassNameError):
    """A ``"__class__"`` value that is not a str, or is badly written: ``problem`` says what it
    must be, and the reason puts the key before it."""

    def __init__(self, problem: str) -> None:
        super().__init__(f"'__class__' {problem}")
        self.problem = problem


def load_class(text: object, home: str) -> type:
    """The class ``text`` names, a bare name read in the module ``home``.

    A raise or a ``SystemExit`` as the module imports, a name the module or
    a class on the way lacks, a raise other than AttributeError as a name is
    read, and a name that reaches something other than a class are each a
    ``ClassNameError``. A text that is not a str or is badly written is a
    ``ClassFormError``. A KeyboardInterrupt goes on, as a Ctrl-C does.
    """
    module_name, qualname = class_parts(text, home)
    try:
        found: object = importlib.import_module(module_name)
    except (Exception, SystemExit) as error:
        raise ClassNameError(f"cannot import {module_name}: {error!r}") from error
    try:
        for part in qualname.split("."):
            found = getattr(found, part)
    except AttributeError as error:
        raise ClassNameError(f"{module_name} has no class {qualname}") from error
    except (Exception, SystemExit) as error:
        raise ClassNameError(f"cannot read {module_name}::{qualname}: {error!r}") from error
    if not is_a_class(found):
        raise ClassNameError(f"{module_name}::{qualname} is not a class")
    return found


def class_parts(text: object, home: str) -> tuple[str, str]:
    """The module and the dotted name a ``"__class__"`` text names, the bare name's module
    ``home``, read without importing anything. A text that is not a str or is badly written is a
    ``ClassFormError``."""
    if isinstance(text, str):
        module_name, joined, qualname = text.partition("::")
        if not joined:
            module_name, qualname = home, text
        if _dotted(module_name) and _dotted(qualname):
            return module_name, qualname
    raise ClassFormError(f"must be MODULE::CLASS or a class name, got {written(text)}")


def _dotted(name: str) -> bool:
    """Whether ``name`` is one or more identifiers joined by dots."""
    return all(part.isidentifier() for part in name.split("."))


def written(value: object) -> str:
    """The value as JSON, as the seed was typed; one whose own type JSON has not, which only a
    ``run()`` caller can give, a tuple or a class say, as its repr, so the line shows that
    type. A JSON type that holds what JSON cannot write is written as its repr too."""
    if type(value) not in _JSON_TYPES:
        return repr(value)
    try:
        return as_typed(value)
    except (TypeError, ValueError):
        return repr(value)


def is_a_class(owner: object) -> TypeGuard[type]:
    """Whether ``owner`` is a class, told by its type alone: ``isinstance`` would read
    ``__class__``, which an object's own property can answer."""
    return issubclass(type(owner), type)


def signature_of(cls: type) -> inspect.Signature | None:
    """The class's signature as ``constructor`` reads it, read once per class."""
    known = _SIGNATURES.get(id(cls))
    if known is None:
        known = _SIGNATURES[id(cls)] = (cls, constructor(cls))
    return known[1]


def constructor(cls: type) -> inspect.Signature | None:
    """The class's signature, or None when Python cannot read it.

    Reading it can run the class's own code, as a target's signature can,
    so any Exception or a SystemExit means the same: no signature to read.
    """
    try:
        return inspect.signature(cls)
    except (Exception, SystemExit):
        return None


def is_a_protocol(cls: type) -> bool:
    """Whether ``cls`` is a Protocol, by the mark typing sets on one, which
    ``typing.is_protocol`` reads on 3.13 and later."""
    return getattr(cls, "_is_protocol", False) is True


def hinted_classes(check: Builds | NoOneClass) -> tuple[type, ...]:
    """The classes a class hint names: the one it builds, or those of one that names no one
    class."""
    return (check.cls,) if isinstance(check, Builds) else check.classes


def fits_hint(named: type, check: Builds | NoOneClass) -> bool:
    """Whether a class a ``"__class__"`` names fits a class hint: it is one of the classes the
    hint names, or a subclass of one, as ``issubclass`` says, so a class an ABC registers fits.

    Any class fits a Protocol, which a class usually satisfies by its methods without
    inheriting from it, and pyct cannot tell that fit. A subclass test that raises, as a
    metaclass's own may, counts as a fit too: pyct refuses only what it can show.
    """
    return any(
        is_a_protocol(each) or each is named or _subclass(named, each)
        for each in hinted_classes(check)
    )


def _subclass(named: type, cls: type) -> bool:
    try:
        return issubclass(named, cls)
    except Exception:
        return True
