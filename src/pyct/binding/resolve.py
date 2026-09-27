"""An annotation stored as text, read in every module whose names it could have been written in.

``pyct run``'s seed checks and ``pyct sweep``'s seeds both read text
annotations here, in the same modules and by the same agreement rule. Each
says what it makes of an annotation, and agreement is on that.
"""

import functools
import inspect
import sys
from collections.abc import Callable

from pyct.binding.annotations import Check, check_of


def checked_annotations(
    signature: inspect.Signature, fn: Callable[..., object]
) -> dict[str, Check]:
    """The parameters whose annotation asks something of the seed, and what it asks.

    What an annotation asks, and which annotations ask nothing, is
    ``check_of``'s to say.

    Each annotation is resolved on its own, so one name that does not resolve
    costs that parameter alone rather than the whole function. An annotation
    kept as text, which is what ``from __future__ import annotations`` leaves
    behind, is resolved in every module the text could have been written in:
    the target's, each wrapper's, and the one supplying an ``__init__``,
    ``__new__`` or ``__call__`` the target did not write itself, a base's or
    a metaclass's. It is kept only when every
    module that knows the name reads it as asking the same. A name no module
    resolves, or that two modules resolve differently, skips its own
    parameter and no other. An annotation that asks nothing, such as
    ``str | None`` or a class, is not kept.

    The parameters come from ``signature``, the one the caller already read
    for ``fn``, the same one the seed's fit check reads, so a class target is
    read at its ``__init__`` and the signature is not read again.
    """
    hints: dict[str, Check] = {}
    for name, parameter in signature.parameters.items():
        if parameter.annotation is inspect.Parameter.empty:
            continue
        check = resolved(parameter.annotation, fn, check_of)
        if check is not None:
            hints[name] = check
    return hints


def resolved[T](annotation: object, fn: object, read: Callable[[object], T]) -> T | None:
    """What ``read`` makes of the annotation, or of what every module that knows its text names.

    A namespace whose eval, or whose ``read``, raises does not know the name
    and says nothing. The answer stands only when something resolved it and
    everything that did reads the same; a disagreement is no answer, as any
    failure is. Two modules can build two ``list[int]`` objects from one
    text, so they agree on what ``read`` makes of the text rather than on the
    object.
    """
    if not isinstance(annotation, str):
        return read(annotation)
    answers: list[T] = []
    for names in _namespaces(fn):
        try:
            answers.append(read(eval(annotation, names)))
        except Exception:
            continue
    if not answers or any(answer != answers[0] for answer in answers):
        return None
    return answers[0]


def _namespaces(fn: object) -> list[dict[str, object]]:
    """Every module's names the annotation text on ``fn`` could have been written against.

    Which module ``inspect.signature`` took the text from is not knowable
    from the outside: picking one went wrong round after round. So every
    module that could have written it answers and agreement decides. An
    extra namespace costs at most a skipped check; a missing one could
    refuse a seed the target accepts.
    """
    if isinstance(fn, functools.partial):
        return _namespaces(fn.func)
    spaces: list[dict[str, object]] = []
    for owner in _owners(fn):
        for step in _chain(owner):
            names = getattr(step, "__globals__", None)
            # a slot wrapper such as object.__init__ carries none, and names nothing
            if isinstance(names, dict):
                spaces.append(names)
    spaces.extend(_module_names(fn))
    # by identity: a namespace reached twice is one namespace, and a dict is unhashable
    return list({id(names): names for names in spaces}.values())


def _owners(fn: object) -> list[object]:
    """The callables whose globals could hold ``fn``'s annotation text.

    A class is read at the ``__init__`` and ``__new__`` attribute lookup
    gives, so an inherited one is the base's function, and at its
    metaclass's ``__call__``, which ``inspect.signature`` prefers to both
    when there is one. For an ordinary class that is ``type.__call__``, a
    slot wrapper naming nothing. Which of the three ``inspect.signature``
    picks is its business; all three are candidates here.

    A callable object is a candidate beside its ``__call__``, because a
    class-based decorator sets ``__wrapped__`` by hand and it hangs on the
    object rather than on the method.
    """
    if isinstance(fn, type):
        return [
            getattr(fn, "__init__", None),
            getattr(fn, "__new__", None),
            getattr(type(fn), "__call__", None),  # noqa: B004 - the function, not a test
        ]
    method = getattr(fn, "__func__", None)
    if method is not None:
        return [method]
    if not inspect.isroutine(fn):
        return [fn, getattr(type(fn), "__call__", None)]  # noqa: B004 - the function, not a test
    return [fn]


def _chain(fn: object) -> list[object]:
    """``fn`` and everything its ``__wrapped__`` chain reaches. A cycle ends the walk.

    ``inspect.signature`` follows this chain, except that a wrapper
    declaring its own ``__signature__`` stops it there. Walking the whole
    chain covers the text wherever it was written, without asking which.
    """
    steps: list[object] = []
    seen: set[int] = set()
    step = fn
    while step is not None and id(step) not in seen:
        seen.add(id(step))
        steps.append(step)
        step = getattr(step, "__wrapped__", None)
    return steps


def _module_names(fn: object) -> list[dict[str, object]]:
    """The names of the modules ``fn`` says it was written in.

    A class and a callable object carry no globals of their own, so the
    module each names is what stands in for them.
    """
    named = [getattr(fn, "__module__", None)]
    if not isinstance(fn, type) and not inspect.isroutine(fn):
        named.append(getattr(type(fn), "__module__", None))
    modules = [sys.modules.get(name) for name in named if isinstance(name, str)]
    return [vars(module) for module in modules if module is not None]
