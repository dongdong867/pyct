"""Turn ``module::function`` into the callable it names."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType

from pyct.binding.call import positional_only
from pyct.binding.resolve import checked_annotations
from pyct.execution.execute import ExecutionContext
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
    for any other callable. The seed's value for ``self`` is passed as given.
    """

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature
    import_lines: frozenset[int] = frozenset()
    self_class: type | None = None


def load_target(
    spec: str, watch: ImportWatch | None = None, *, keep_import_lines: bool = True
) -> Target:
    """Import ``module`` from the current directory and follow ``name`` from it.

    ``name`` is one or more names joined by dots, each read as an attribute of
    the last, as ``getattr`` reads it (``follow``).

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
    return Target(
        spec=spec,
        fn=fn,
        file=file,
        signature=signature,
        import_lines=frozenset(ran),
        self_class=self_class,
    )


def execution_context(target: Target, *, alone: bool = False) -> ExecutionContext:
    """What each input of ``target`` calls: its callable and file, the parameters passed by
    position, and what their annotations check. ``alone`` as ``ExecutionContext`` says."""
    positional = positional_only(target.signature)
    checks = checked_annotations(target.signature, target.fn)
    return ExecutionContext(
        target.fn, target.file, alone=alone, positional=positional, checks=checks
    )


def follow(module: object, name: str) -> object:
    """What ``name``, names joined by dots, reaches from ``module``, read one attribute at a time.

    A read raises as ``getattr`` raises, an AttributeError for a name the
    object lacks.
    """
    found = module
    for part in name.split("."):
        found = getattr(found, part)
    return found


def _followed(spec: str, module: ModuleType) -> tuple[Callable[..., object], type | None]:
    """The callable the spec's name reaches from ``module``, and the class it needs as ``self``.

    A name the object lacks, or one that reaches nothing callable, is a
    ``TargetError`` that says the module has no such function. Any other
    raise, or a ``SystemExit``, as a read runs the target's own code, such as
    a property, is a ``TargetError`` that gives ``_reason`` for it.
    """
    module_name, _, name = spec.partition("::")
    owner_name, _, last = name.rpartition(".")
    missing = f"{module_name} has no function {name}"
    try:
        owner = follow(module, owner_name) if owner_name else module
        fn = getattr(owner, last)
    except AttributeError as error:
        raise TargetError(missing) from error
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot read {spec}: {_reason(error)}") from error
    if not callable(fn):
        raise TargetError(missing)
    return fn, _self_class(owner, last)


def _self_class(owner: object, name: str) -> type | None:
    """``owner`` when it is a class whose attribute ``name`` binds to an instance read through it.

    That is the first object its classes hold under ``name``, in the order
    Python looks them up: one whose type has ``__get__``, other than a
    staticmethod or a classmethod, which bind to no instance. A name only
    the class's own type holds, as ``mro``, is bound to the class already.
    """
    if not isinstance(owner, type):
        return None
    for base in inspect.getmro(owner):
        if name in vars(base):
            held = vars(base)[name]
            binds = hasattr(type(held), "__get__")
            return owner if binds and not isinstance(held, (staticmethod, classmethod)) else None
    return None


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
