"""Count-equality branch target with a literal substring.

The branch ``s.count("ab") == 2`` requires the engine to synthesize an
input whose literal-substring count equals a concrete integer. The
seed value ``"xx"`` yields ``count("ab") == 0`` so the engine must
flip the branch by producing an ``s`` containing the literal twice.
"""


def has_two_ab(s: str) -> str:
    if s.count("ab") == 2:
        return "match"
    return "nomatch"
