"""Turn ``module::function`` into the callable it names."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import TypeGuard

from pyct.binding.annotations import Check, Fields
from pyct.binding.call import positional_only
from pyct.binding.resolve import checked_annotations
from pyct.execution.blame import one_line
from pyct.execution.execute import ExecutionContext, SelfBuild
from pyct.intercept.cache import cache_folder
from pyct.intercept.hook import Interception, intercepting
from pyct.run.import_lines import import_lines
from pyct.run.import_watch import ImportWatch
from pyct.run.own_imports import keep_own_imports

# the two exceptions inspect raises when it cannot read a signature; one of exactly these types
# reads by its message alone
_INSPECT_S_OWN = (ValueError, TypeError)


class TargetError(Exception):
    """The target could not be loaded, and the message says why.

    The module does not import, its name leads to no function or raises as it
    is read, the module has no Python source, or Python cannot read the
    function's signature.
    """


@dataclass(frozen=True)
class Target:
    """A loaded target: its spec, the callable, the file it lives in, and its signature.

    ``import_lines`` is the lines of the file that ran while ``load_target``
    imported the module, which count for the run as covered. A module Python
    had already imported, by a ``run()`` caller or by pyct itself, such as
    ``json``, runs no line again, so it has none.

    ``self_class`` is the class the spec names before a method that Python
    binds to an instance read through that class, such as ``Cart`` for
    ``Cart.total``: the method takes an instance of it as ``self``. It is None
    for a callable read through the class that is bound to it already, or
    that the class holds without binding. A descriptor that returns a callable
    of its own when read through the class, bound to nothing, counts as one
    that binds to an instance, since only an instance would tell the two
    apart.

    ``self_name`` is that method's first parameter, when it takes a position:
    the seed's key for the constructor's arguments, from which each input
    builds the instance. With none, nothing is built, and the seed's value
    for the method's parameters is passed as given. ``constructor`` is the
    class's signature, as Python reads it at load, or None when Python
    cannot read it; the instance is still built then.

    ``followed`` is the spec ``load_target`` followed and the callable it
    reached, which a fresh interpreter finds by following that spec again.
    A target built by hand has none, and a caller who changes ``spec`` or
    ``fn`` leaves it as it was, so it then speaks for neither.
    """

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature
    import_lines: frozenset[int] = frozenset()
    self_class: type | None = None
    followed: tuple[str, Callable[..., object]] | None = None
    self_name: str | None = None
    constructor: inspect.Signature | None = None


def load_target(
    spec: str, watch: ImportWatch | None = None, *, keep_import_lines: bool = True
) -> Target:
    """Import ``module`` from the current directory and follow ``name`` from it.

    ``name`` is one or more names joined by dots, each read once as an
    attribute of the last, as ``getattr`` reads it.

    The working directory goes first on the import path, so a module under
    it resolves with no ``PYTHONPATH`` set. From then on, a module pyct
    imports for itself is looked for in the standard library first
    (``own_imports``). While the module imports, ``watch`` names it for
    the process that watches this one, when one does. With
    ``keep_import_lines``, the lines of the module that run as it imports
    are kept on the target; an input's fresh interpreter, whose import is not
    the run's, keeps none.
    """
    module_name = spec.partition("::")[0]
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    keep_own_imports(module_name.partition(".")[0])
    keeping = import_lines(module_name) if keep_import_lines else contextlib.nullcontext(set())
    with keeping as ran:
        module = _imported(module_name, watch)
    fn, self_class = _followed(spec, module)
    file = getattr(module, "__file__", None)
    if file is None or not file.endswith(".py"):
        raise TargetError(f"{module_name} has no Python source file")
    signature = _signature(spec, fn)
    self_name = None if self_class is None else _self_name(signature)
    return Target(
        spec=spec,
        fn=fn,
        file=file,
        signature=signature,
        import_lines=frozenset(ran),
        self_class=self_class,
        followed=(spec, fn),
        self_name=self_name,
        constructor=None if self_class is None or self_name is None else _constructor(self_class),
    )


def execution_context(target: Target, *, alone: bool = False) -> ExecutionContext:
    """What each input of ``target`` calls: its callable and file, the parameters passed by
    position, what their annotations check, and how it builds the instance a method runs on.
    ``alone`` as ``ExecutionContext`` says."""
    return ExecutionContext(
        target.fn,
        target.file,
        alone=alone,
        positional=positional_only(target.signature),
        checks=argument_checks(target),
        builds=_builds(target),
    )


def argument_checks(target: Target) -> dict[str, Check]:
    """What each parameter's annotation asks of the seed.

    For a method whose instance each input builds, the value under its first
    parameter holds the constructor's arguments, whose keys stay fixed and
    whose values the constructor's annotations check (``Fields``).
    """
    checks = checked_annotations(target.signature, target.fn)
    if target.self_class is None or target.self_name is None:
        return checks
    constructor = target.constructor
    each = {} if constructor is None else checked_annotations(constructor, target.self_class)
    return {**checks, target.self_name: Fields(each)}


def _builds(target: Target) -> SelfBuild | None:
    """How each input builds the instance the target's method runs on, or None for a target
    that needs none built."""
    if target.self_class is None or target.self_name is None:
        return None
    constructor = target.constructor
    positional = () if constructor is None else positional_only(constructor)
    return SelfBuild(target.self_class, target.self_name, positional)


def _self_name(signature: inspect.Signature) -> str | None:
    """The method's first parameter, which Python passes the instance to, when it takes a
    position; None for a method whose first parameter takes none, or that has none."""
    first = next(iter(signature.parameters.values()), None)
    positions = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return first.name if first is not None and first.kind in positions else None


def _constructor(cls: type) -> inspect.Signature | None:
    """The class's signature, or None when Python cannot read it.

    Reading it can run the class's own code, as ``_signature`` says, so any
    Exception or a SystemExit means the same: no signature to read.
    """
    try:
        return inspect.signature(cls)
    except (Exception, SystemExit):
        return None


def _followed(spec: str, module: ModuleType) -> tuple[Callable[..., object], type | None]:
    """The callable the spec's name reaches from ``module``, and the class it needs as ``self``.

    A name the object lacks, or one that reaches nothing callable, is a
    ``TargetError`` that says the module has no such function. Any other
    raise, or a ``SystemExit``, as a read runs the target's own code, such as
    a property, is a ``TargetError`` that names it on one line, its type
    first, as pyct reports any raise of the target's.
    """
    module_name, _, name = spec.partition("::")
    missing = f"{module_name} has no function {name}"
    try:
        owner, fn = _walked(module, name)
    except AttributeError as error:
        raise TargetError(missing) from error
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot read {spec}: {one_line(error)}") from error
    if not callable(fn):
        raise TargetError(missing)
    return fn, _self_class(owner, name.rpartition(".")[2], fn)


def _walked(module: ModuleType, name: str) -> tuple[object, object]:
    """The object before ``name``'s last part, and what that part reads as. Each name is read
    once, and raises as ``getattr`` raises."""
    owner: object = module
    found: object = module
    for part in name.split("."):
        owner = found
        found = getattr(owner, part)
    return owner, found


def _has_get(kind: type) -> bool:
    """Whether Python reads an object of ``kind`` through its ``__get__``: along ``kind``'s own
    classes, never ``kind``'s type."""
    return any("__get__" in vars(base) for base in inspect.getmro(kind))


def _self_class(owner: object, name: str, fn: object) -> type | None:
    """``owner`` when it is a class whose attribute ``name`` binds to an instance read through it.

    That is the first object its classes hold under ``name``, in the order
    Python looks them up: one whose type has ``__get__``, other than a
    staticmethod or a classmethod, which bind to no instance. Python 3.12
    reads a classmethod that wraps a staticmethod as its plain function, so
    the classmethod is told by what the class holds. ``fn``, the attribute
    as read through the class, is bound to the class already for a
    classmethod written in C, and for any other descriptor that binds to
    the class it is read through. A name only the class's own type holds,
    as ``mro``, is bound to the class too.
    """
    if not _is_a_class(owner) or _bound_to(fn, owner):
        return None
    for base in inspect.getmro(owner):
        if name in vars(base):
            held = vars(base)[name]
            unbinding = issubclass(type(held), (staticmethod, classmethod))
            return owner if _has_get(type(held)) and not unbinding else None
    return None


def _is_a_class(owner: object) -> TypeGuard[type]:
    """Whether ``owner`` is a class, told by its type alone: ``isinstance`` would read
    ``__class__``, which an object's own property can answer."""
    return issubclass(type(owner), type)


def _bound_to(fn: object, owner: type) -> bool:
    """Whether ``fn`` is a method, written in Python or in C, bound to ``owner`` itself."""
    method = type(fn) in (types.MethodType, types.BuiltinMethodType)
    return method and getattr(fn, "__self__", None) is owner


def _imported(module_name: str, watch: ImportWatch | None) -> ModuleType:
    """The module, imported. A raise or a ``SystemExit`` at its import is a ``TargetError``.

    Either reads by its repr. A KeyboardInterrupt goes on to end pyct, as a
    Ctrl-C does.
    """
    importing = contextlib.nullcontext() if watch is None else watch.importing(module_name)
    try:
        with importing:
            return importlib.import_module(module_name)
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot import {module_name}: {error!r}") from error


def _signature(spec: str, fn: Callable[..., object]) -> inspect.Signature:
    """``fn``'s signature. A raise or a ``SystemExit`` as it is read is a ``TargetError``.

    Reading a signature can run the target's own code, such as an attribute
    lookup or, from Python 3.14, an annotation's evaluation, so any
    Exception can come of it, or a SystemExit. The refusal gives ``_reason``
    for it. A KeyboardInterrupt, or pyct's own stop, goes on to end pyct.
    """
    try:
        return inspect.signature(fn)
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot read the signature of {spec}: {_reason(error)}") from error


def _reason(error: BaseException) -> str:
    """Python's message for ``error`` as one line that is never empty.

    That is the message's first line that holds anything. A ValueError or a
    TypeError reads by that line alone, as inspect's own refusals do; any
    other exception, a subclass of those two included, is named before it,
    as ``SystemExit: 0`` and ``UnicodeError: bad text``. A message with no
    such line gives the type's name alone, and so does one that cannot be
    read, since its ``__str__`` raises. So the refusal stays one line on
    stderr.
    """
    named = type(error).__name__
    try:
        message = str(error)
    except Exception:
        return named
    lines = [line for line in message.splitlines() if line.strip()]
    if not lines:
        return named
    return lines[0] if type(error) in _INSPECT_S_OWN else f"{named}: {lines[0]}"


def interception(spec: str) -> contextlib.AbstractContextManager[None]:
    """The block that substitutes the target's package, for the owner of a run to hold open.

    The spec's module names the package. Its code is kept in the cache
    folder as it is when the block opens.
    """
    return intercepting(Interception(module=spec.partition("::")[0], cache=cache_folder()))
