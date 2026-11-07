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

from pyct.binding.call import positional_only
from pyct.binding.resolve import checked_annotations
from pyct.execution.blame import one_line
from pyct.execution.execute import ExecutionContext
from pyct.intercept.cache import cache_folder
from pyct.intercept.hook import Interception, intercepting
from pyct.run.import_lines import import_lines
from pyct.run.import_watch import ImportWatch
from pyct.run.own_imports import keep_own_imports

# the two exceptions inspect raises when it cannot read a signature; one of exactly these types
# reads by its message alone
_INSPECT_S_OWN = (ValueError, TypeError)


# what Python reads through a ``__get__`` of its own: a function, a staticmethod, a method or
# slot a type written in C holds, a ``__slots__`` slot, and a C type's own attribute
_PYTHON_S_BINDINGS = (
    types.FunctionType,
    staticmethod,
    types.ClassMethodDescriptorType,
    types.MethodDescriptorType,
    types.WrapperDescriptorType,
    types.MemberDescriptorType,
    types.GetSetDescriptorType,
)


# what no class holds, told apart from any value one holds
_NOTHING = object()


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
    apart. The seed's value for ``self`` is passed as given.

    ``found_by_name`` is the callable the spec's name reached, when each read
    along it ran Python's own lookup alone (``_read_plainly``), so another
    interpreter that follows the name finds the same callable without
    running the target's code to get there. It is None when a read ran the
    target's code, such as a property. A caller who puts another callable in
    ``fn`` leaves it, so no name finds that one.
    """

    spec: str
    fn: Callable[..., object]
    file: str
    signature: inspect.Signature
    import_lines: frozenset[int] = frozenset()
    self_class: type | None = None
    found_by_name: Callable[..., object] | None = None


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
    fn, self_class, found_by_name = _followed(spec, module)
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
        found_by_name=found_by_name,
    )


def execution_context(target: Target, *, alone: bool = False) -> ExecutionContext:
    """What each input of ``target`` calls: its callable and file, the parameters passed by
    position, and what their annotations check. ``alone`` as ``ExecutionContext`` says."""
    positional = positional_only(target.signature)
    checks = checked_annotations(target.signature, target.fn)
    return ExecutionContext(
        target.fn, target.file, alone=alone, positional=positional, checks=checks
    )


def _followed(
    spec: str, module: ModuleType
) -> tuple[Callable[..., object], type | None, Callable[..., object] | None]:
    """The callable the spec's name reaches from ``module``, the class it needs as ``self``, and
    the callable again when each read ran Python's own lookup alone, else None.

    A name the object lacks, or one that reaches nothing callable, is a
    ``TargetError`` that says the module has no such function. Any other
    raise, or a ``SystemExit``, as a read runs the target's own code, such as
    a property, is a ``TargetError`` that names it on one line, its type
    first, as pyct reports any raise of the target's.
    """
    module_name, _, name = spec.partition("::")
    missing = f"{module_name} has no function {name}"
    try:
        owner, fn, plain = _walked(module, name)
    except AttributeError as error:
        raise TargetError(missing) from error
    except (Exception, SystemExit) as error:
        raise TargetError(f"cannot read {spec}: {one_line(error)}") from error
    if not callable(fn):
        raise TargetError(missing)
    last = name.rpartition(".")[2]
    return fn, _self_class(owner, last, fn), fn if plain else None


def _walked(module: ModuleType, name: str) -> tuple[object, object, bool]:
    """The object before ``name``'s last part, what that part reads as, and whether each read ran
    Python's own lookup alone. Each name is read once, and raises as ``getattr`` raises."""
    owner: object = module
    found: object = module
    plain = True
    for part in name.split("."):
        owner = found
        plain = plain and _read_plainly(owner, part)
        found = getattr(owner, part)
    return owner, found, plain


def _read_plainly(owner: object, name: str) -> bool:
    """Whether reading ``name`` from ``owner`` takes Python's own steps, told without reading it:
    none of the steps this checks runs the target's code.

    The owner's type looks attributes up as Python's built-in types do, and
    the name is held where that lookup finds it rather than given by a
    ``__getattr__``. Python reads a value through its ``__get__`` only when
    a class holds it, along the owner's classes or its type's; a value in a
    module's or an instance's own names is read as it is. A value a class
    holds either has no ``__get__`` or binds by one of Python's own
    (``_PYTHON_S_BINDINGS``). A classmethod is told by what it wraps, which
    Python 3.12 reads through its own ``__get__``.
    """
    if not _pythons_own(inspect.getattr_static(type(owner), "__getattribute__")):
        return False
    try:
        held = inspect.getattr_static(owner, name)
    except AttributeError:
        return False
    if not _held_by_a_class(owner, name, held):
        return True
    while type(held) is classmethod:
        held = held.__func__
    return type(held) in _PYTHON_S_BINDINGS or not _has_get(type(held))


def _held_by_a_class(owner: object, name: str, held: object) -> bool:
    """Whether a class holds ``held`` under ``name``: one of the owner's own classes, when it is
    a class, or one of its type's."""
    classes = [*(inspect.getmro(owner) if isinstance(owner, type) else ()), *type(owner).__mro__]
    return any(vars(kind).get(name, _NOTHING) is held for kind in classes)


def _pythons_own(lookup: object) -> bool:
    """Whether an attribute lookup is one of Python's built-in types' own, written in C."""
    owner = (
        getattr(lookup, "__objclass__", None)
        if type(lookup) is types.WrapperDescriptorType
        else None
    )
    return isinstance(owner, type) and owner.__module__ == "builtins"


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
    if not isinstance(owner, type) or _bound_to(fn, owner):
        return None
    for base in inspect.getmro(owner):
        if name in vars(base):
            held = vars(base)[name]
            plain = isinstance(held, (staticmethod, classmethod))
            return owner if _has_get(type(held)) and not plain else None
    return None


def _bound_to(fn: object, owner: type) -> bool:
    """Whether ``fn`` is a method, written in Python or in C, bound to ``owner`` itself."""
    method = isinstance(fn, (types.MethodType, types.BuiltinMethodType))
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
