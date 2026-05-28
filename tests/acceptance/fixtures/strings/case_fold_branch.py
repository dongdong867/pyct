"""Case-fold equality branch target with an ASCII literal.

The branch ``s.lower() == "monday"`` requires the engine to synthesize
an input whose case-folded form equals a concrete ASCII literal. The
seed value ``"x"`` yields ``"x".lower() == "monday"`` False, so the
engine must flip the branch by producing an ``s`` whose lowercased form
equals ``"monday"`` exactly.
"""


def matches_monday(s: str) -> str:
    if s.lower() == "monday":
        return "match"
    return "nomatch"
