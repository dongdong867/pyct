"""Per-char ``int()`` witness — drives ConcolicStr per-character int routing.

The ``hit`` arm requires ``digits[1] == 7``. Reaching it depends on two
things landing together: ``map(int, s)`` AST-rewriting to a per-character
comprehension so each character flows through ``ConcolicInt.__new__``,
and ``ConcolicInt.__new__`` dispatching on a single-char ``ConcolicStr``
to emit a symbolic ``(- (str.to_code s) 48)`` expression that links the
resulting int back to the originating character of ``s``.

If either piece is missing, ``map(int, s)`` produces a plain Python list
of ints with no symbolic provenance and the engine cannot synthesize a
character of ``s`` that flips the branch.

Anchors the ``per-char-int-branches`` AC.
"""


def per_char_target(s: str) -> str:
    digits = list(map(int, s))
    if digits[1] == 7:
        return "hit"
    return "miss"
