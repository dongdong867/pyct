"""Membership fixture where each matched element reaches a distinct
downstream code path.

The branch ``x in {"red", "green", "blue", "yellow"}`` has N=4 literal
container elements. Unlike ``membership_set.matches_color`` which
collapses every match to a single ``return "match"`` line, this fixture
routes each matched element to its own ``return`` statement on a
distinct source line. That makes every successful disjunct flip yield
fresh line coverage: the first match covers one return line, the
second match covers a different return line, etc.

This shape anchors the
``chain-stays-productive-when-each-match-distinct`` AC: because each
flip gains new coverage, the chain's unproductive-streak counter
should never cross the deprioritization threshold, so
``gen_chain_deprioritized`` must remain 0 for this run.

The seed value ``"none"`` matches no container element, forcing the
engine to flip each disjunct in turn to exercise the four distinct
return paths.
"""


def chain_with_distinct_paths(x: str) -> str:
    if x in {"red", "green", "blue", "yellow"}:
        if x == "red":
            return "ruby"
        if x == "green":
            return "emerald"
        if x == "blue":
            return "sapphire"
        return "citrine"
    return "nomatch"
