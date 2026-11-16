"""The lines of ``splitlines()``, written as fresh strings glued together:
s = p0 ++ b0 ++ p1 ++ b1 ++ … ++ pi ++ bi ++ rest.

Line i written as i nested searches, each from the end of the last (`splits`), took cvc5 1.4.2
about 10 s at line 19 and ran past its limit from line 39; the same ask written glued answered
in hundredths of a second at line 19 and in 0.1 s at line 199
(a-later-split-piece-is-written-as-glued-pieces).

Each step cuts what is left of the string, ``left!N!i``, the string itself at step 0, into a
piece, the gap after it, and what is left after them, ``left!N!i+1``. The piece is a line and
the gap its line break, "\\r\\n" one break. A step's facts hold of exactly one cut of any
string: a line stops at the first break, a "\\r" break is never followed by "\\n", and an empty
gap leaves nothing after it. So past the string's last line every later piece, gap and rest is
empty. The facts never rule out a string, so they are asserted on every path, and that line i
is there, something is left at step i, is a term a fork may negate; a break at the very end
starts no line.

Names follow the definitions index when a split's first piece is read, as ``e!N`` does, under
prefixes of their own: ``piece!N!i``, ``gap!N!i`` and ``left!N!i``.
"""

from pyct.solver.checks import one_of, outside
from pyct.solver.splits import LINE_BREAKS
from pyct.solver.strings import encode

# what may sit after a line: one line break, "\r\n" one, or nothing past the last line
_LINE_GAP = f'(re.union (str.to_re "") (str.to_re {encode("\r\n")}) {one_of(LINE_BREAKS)})'
_IN_A_LINE = f"(re.* {one_of(outside(LINE_BREAKS))})"


def glues(head: str, operands: tuple[object, ...]) -> bool:
    """Whether a split's pieces are read glued: ``splitlines``."""
    return head == "splitlines"


class Glued:
    """One split's pieces, declared in ``declared`` step by step as far as a read reaches.

    ``term`` is the string's term, ``head`` and ``operands`` the split as core wrote it.
    """

    def __init__(
        self, term: str, head: str, operands: tuple[object, ...], declared: list[str]
    ) -> None:
        self.term, self.declared = term, declared
        self.keep = bool((*operands, False)[0])
        self.prefix = ""
        self.steps = 0

    def piece(self, index: int) -> str:
        """Line ``index``, with its break where they are kept."""
        self._reach(index)
        piece = self._name("piece", index)
        if self.keep:
            return f"(str.++ {piece} {self._name('gap', index)})"
        return piece

    def there(self, index: int) -> str:
        """That line ``index`` is there: something is left before it."""
        self._reach(index)
        return f'(not (= {self._name("left", index)} ""))'

    def _name(self, kind: str, index: int) -> str:
        """The name of a step's piece, gap or what is left; at step 0 what is left is the
        string."""
        return self.term if kind == "left" and index == 0 else f"{kind}!{self.prefix}!{index}"

    def _reach(self, index: int) -> None:
        """Declare each step up to ``index``, once."""
        if not self.prefix:
            self.prefix = str(len(self.declared))
        while self.steps <= index:
            self.declared += self._step(self.steps)
            self.steps += 1

    def _step(self, at: int) -> list[str]:
        """The declarations and facts of step ``at``."""
        piece, gap = self._name("piece", at), self._name("gap", at)
        left, after = self._name("left", at), self._name("left", at + 1)
        lines = [f"(declare-const {name} String)" for name in (piece, gap, after)]
        facts = [
            f"(= {left} (str.++ {piece} {gap} {after}))",
            f"(str.in_re {piece} {_IN_A_LINE})",
            f"(str.in_re {gap} {_LINE_GAP})",
            f'(=> (= {gap} "") (= {after} ""))',
            f"(=> (= {gap} {encode('\r')}) (not (str.prefixof {encode('\n')} {after})))",
        ]
        return lines + [f"(assert {fact})" for fact in facts]
