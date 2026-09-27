"""Python's floor division and modulo on ints in SMT-LIB.

SMT-LIB's `div` and `mod` are Euclidean: the remainder is never negative.
Python floors toward minus infinity and its `%` takes the divisor's sign.
The two agree when the divisor is positive or the remainder is zero;
otherwise Python's quotient is one lower and its remainder is shifted by the
divisor. Render writes each as an ite on those two facts; decision
division-floor-correction-in-render.
"""


def floor_division(dividend: str, divisor: str) -> str:
    """Python's ``//`` on two Int terms."""
    quotient = f"(div {dividend} {divisor})"
    return f"(ite {_euclidean_agrees(dividend, divisor)} {quotient} (- {quotient} 1))"


def modulo(dividend: str, divisor: str) -> str:
    """Python's ``%`` on two Int terms."""
    remainder = f"(mod {dividend} {divisor})"
    return f"(ite {_euclidean_agrees(dividend, divisor)} {remainder} (+ {remainder} {divisor}))"


def _euclidean_agrees(dividend: str, divisor: str) -> str:
    """When SMT-LIB's division is already Python's: a positive divisor, or nothing left over."""
    return f"(or (> {divisor} 0) (= (mod {dividend} {divisor}) 0))"
