"""Python floats in SMT-LIB: a double literal both ways, and the forms no one operator spells.

A tracked float is an IEEE-754 double in cvc5's floating-point theory, and
every operation render writes rounds to nearest even, as CPython does, so an
answer takes the side it aimed for to the last bit; decision
float-ieee-double-in-cvc5.

A literal is written as the double's own bit pattern, ``(fp #bS #bE #bF)``:
the sign, the eleven exponent bits and the fifty-two fraction bits. No
decimal is rounded on the way, and -0.0, the subnormals, the infinities and
NaN are written like any other double. cvc5 prints a Float64 value in the
same form, so reading one back undoes the step exactly.

``==`` and ``!=`` are IEEE equality, ``fp.eq``, as Python's are. SMT-LIB's
``=`` is sameness instead: on cvc5 1.3.4 it calls NaN equal to itself and
tells -0.0 from 0.0.

``whole`` is ``float.is_integer``: a finite double its integral part
equals. It is false on NaN, where ``fp.eq`` is, and on the infinities.
``finite`` holds for a double that is neither NaN nor an infinity.
"""

import re
import struct

# a double's three fields as cvc5 prints them: one sign bit, eleven exponent bits, fifty-two
# fraction bits
_VALUE = re.compile(r"\(fp #b(?P<sign>[01]) #b(?P<exponent>[01]{11}) #b(?P<fraction>[01]{52})\)")


def literal(value: float) -> str:
    """The SMT-LIB term cvc5 reads as exactly this double: its bit pattern."""
    (bits,) = struct.unpack(">Q", struct.pack(">d", value))
    text = f"{bits:064b}"
    return f"(fp #b{text[0]} #b{text[1:12]} #b{text[12:]})"


def decode(text: str) -> float:
    """The double a Float64 value, as cvc5 prints it, holds."""
    matched = _VALUE.fullmatch(text)
    if matched is None:
        raise ValueError(f"not a double in three fields: {text}")
    bits = int(matched["sign"] + matched["exponent"] + matched["fraction"], 2)
    (value,) = struct.unpack(">d", bits.to_bytes(8, "big"))
    return value


def finite(term: str) -> str:
    """``term`` is neither NaN nor an infinity."""
    return f"(not (or (fp.isNaN {term}) (fp.isInfinite {term})))"


def unequal(left: str, right: str) -> str:
    """Python's ``!=`` on two doubles: not IEEE equal, so NaN is unequal to itself."""
    return f"(not (fp.eq {left} {right}))"


def minus(*operands: str) -> str:
    """Python's ``-``: the negation of one operand, or the difference of two."""
    if len(operands) == 1:
        return f"(fp.neg {operands[0]})"
    return f"(fp.sub RNE {' '.join(operands)})"


def whole(term: str) -> str:
    """Python's ``float.is_integer``: finite, and equal to its integral part."""
    return f"(and (not (fp.isInfinite {term})) (fp.eq (fp.roundToIntegral RTZ {term}) {term}))"
