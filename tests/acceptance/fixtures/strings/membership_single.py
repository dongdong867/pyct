"""Single-element membership branch targets.

Three callables sharing identical downstream branching: a single-element
literal set, a single-element literal tuple, and a plain ``==`` baseline
against the same literal. The membership rewrite collapses
``x in {"a"}`` and ``x in ("a",)`` into the bare ``Compare(Eq)`` form
emitted directly — observationally equivalent to ``x == "a"``.

This anchors the ``membership-single-element`` AC: for a target with
``x in {"a"}`` or ``x in ("a",)``, the path-condition emitted is the
same as for ``x == "a"``, and the engine generates the same set of
inputs as it would for the ``==`` form on the same target.
"""


def in_single_set(x: str) -> str:
    if x in {"a"}:
        return "match"
    return "nomatch"


def in_single_tuple(x: str) -> str:
    if x in ("a",):
        return "match"
    return "nomatch"


def eq_baseline(x: str) -> str:
    if x == "a":
        return "match"
    return "nomatch"
