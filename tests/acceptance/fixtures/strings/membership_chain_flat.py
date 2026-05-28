"""Membership fixture where every matched element collapses to the
same downstream return line.

The branch ``x in {"a", "b", "c", "d", "e", "f", "g", "h"}`` has N=8
literal container elements. Unlike
``membership_chain_productive.chain_with_distinct_paths`` which routes
each matched element to its own ``return`` statement on a distinct
source line, this fixture returns the membership boolean directly with
no per-element downstream branching. Every successful disjunct flip
reaches the same single ``return True`` line, so each successive flip
after the first contributes ZERO new line coverage.

This shape anchors the
``chain-deprioritized-after-unproductive-streak`` AC: after a few
unproductive flips on this chain, the adaptive scheduler should
deprioritize remaining disjuncts and increment
``gen_chain_deprioritized`` once for the chain transition.

The seed value ``"none"`` matches no container element, forcing the
engine to flip disjuncts of the chain. After the first successful
flip covers the ``return True`` line, subsequent flips of the chain
cannot gain new line coverage (the only other line is
``return False`` already covered by the seed), so the chain crosses
the unproductive-streak threshold quickly.
"""


def membership_returns_bool(x: str) -> bool:
    return x in {"a", "b", "c", "d", "e", "f", "g", "h"}
