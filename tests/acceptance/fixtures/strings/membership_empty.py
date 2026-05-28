"""Empty-container membership branch targets.

Each callable below branches on ``x in <empty-container>`` for one of
the three empty-container literal shapes Python supports: ``set()``,
``()`` (empty tuple), and ``[]`` (empty list). Per Python semantics
each of these comparators is always False regardless of ``x``, so no
input can ever reach the ``"match"`` arm.

This anchors the ``membership-empty-container`` AC: the engine should
treat each Compare as a constant False matching Python semantics, and
no branch flip should be registered for the membership Compare. The
rewriter emits ``Constant(False)`` at the rewrite site, which still
counts as a rewrite firing (the ``gen_membership_rewritten`` counter
ticks even though the emitted node is the constant-fold form).
"""


def in_empty_set(x: str) -> str:
    if x in set():  # always False per Python semantics
        return "match"
    return "nomatch"


def in_empty_tuple(x: str) -> str:
    if x in ():
        return "match"
    return "nomatch"


def in_empty_list(x: str) -> str:
    if x in []:
        return "match"
    return "nomatch"
