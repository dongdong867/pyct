"""Where a walk key escapes: no ask on a path where a walk key escaped chooses any key, and the
first escape on the path says so with a fact that keeps its key at the key the input holds there
(let-the-solver-choose-a-small-dict-s-walk-key).

A walk key escapes when Python's own code hashes or compares it (``walk_key_escapes``), and at
every downgrade the input records (``lost``): an operation pyct has not taught may have read any
key the input's walks handed out, so each of them escapes there, whichever operation it was.
Each later escape on the path only marks its key, which compares as its plain key from then on:
a fact for it would hold back no ask the first one does not.
"""

from __future__ import annotations

from typing import Any

from pyct.core.branch import BranchSink, Downgrade, Expression, Fact, caller_site

# the head of a walk key's expression, `["key", A, i]`
WALK_KEY = "key"

# each walk key handed out into a sink and not yet escaped, by the sink's identity, the sink held
# beside them so its identity stays its own; a call that starts empties it (``forget``)
_HANDED: dict[int, tuple[BranchSink, list[object]]] = {}


# each sink that holds a walk key's escape fact, by its identity, the sink held beside it; a
# call that starts empties it (``forget``)
_PINNED: dict[int, BranchSink] = {}


def handed_into(sink: BranchSink, key: object) -> None:
    """Note a walk key handed out into ``sink``: a downgrade recorded there escapes it."""
    _HANDED.setdefault(id(sink), (sink, []))[1].append(key)


def pinned_in(sink: BranchSink) -> bool:
    """Whether a walk key handed out into ``sink`` escaped: no ask on the path past that point
    chooses a key, so a walk from then on hands out keys as before walk keys."""
    return id(sink) in _PINNED


def lost(sink: BranchSink, downgrade: Downgrade) -> None:
    """Record a downgrade, and escape each walk key handed out into the same sink. An escape is
    for good, so the keys leave the registry, and a downgrade inside a walk looks at each key
    once."""
    sink.append(downgrade)
    entry = _HANDED.pop(id(sink), None)
    if entry is not None:
        for key in entry[1]:
            escaped(key)


def forget() -> None:
    """Drop every walk key handed out so far, and every sink's escape fact: a call that starts
    keeps none of an earlier call's keys, nor its sink, alive."""
    _HANDED.clear()
    _PINNED.clear()


def is_walk_key(value: object) -> bool:
    """Whether a value is a walk key: a tracked str or int whose expression is `["key", A, i]`."""
    held = getattr(value, "__dict__", None)
    expression = held.get("expression") if isinstance(held, dict) else None
    return isinstance(expression, list) and expression[:1] == [WALK_KEY]


def has_escaped(value: object) -> bool:
    """Whether a value is a walk key that escaped."""
    held = getattr(value, "__dict__", None)
    return isinstance(held, dict) and bool(held.get("escaped"))


def escaped(value: object) -> None:
    """Note that a walk key escapes, once for each key a walk hands out, and, for the first
    escape into its sink, the fact that it is the key the input holds at its pass. Any other
    value is left as it is."""
    if not is_walk_key(value) or has_escaped(value):
        return
    held: dict[str, Any] = value.__dict__
    held["escaped"] = True
    sink: BranchSink = held["sink"]
    if id(sink) in _PINNED:
        return
    _PINNED[id(sink)] = sink
    bare = bare_key(value)
    written: Expression = str.__repr__(bare) if isinstance(bare, str) else int.__int__(bare)  # pyrefly: ignore[bad-argument-type]
    sink.append(Fact(["==", held["expression"], written], True, caller_site()))


def bare_key(value: object) -> object:
    """A walk key's plain value, an exact str or int; any other value as it is."""
    if not is_walk_key(value):
        return value
    return str.__str__(value) if isinstance(value, str) else int.__int__(value)  # pyrefly: ignore[bad-argument-type]
