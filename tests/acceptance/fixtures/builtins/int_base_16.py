"""Non-default-base ``int(s, 16)`` witness — must skip symbolic tracking.

The ``ConcolicCallRewriter`` only rewrites ``int(x)`` calls whose
positional arity is exactly one with no keywords. A second positional
arg (the base, here ``16``) falls outside that shape, so the rewrite
is skipped and the call goes to Python's primitive ``int`` builtin
unchanged — no ``ConcolicStr.to_int`` dispatch, no
``gen_str_to_int_singleton_rewritten`` counter bump.

Anchors the ``non-default-base-int-skipped`` AC.
"""


def parse_hex(s: str) -> str:
    try:
        n = int(s, 16)
    except ValueError:
        return "invalid"
    if n == 0:
        return "zero"
    return "nonzero"
