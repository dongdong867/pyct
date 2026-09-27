import math
import struct

import pytest

from pyct.solver.floats import decode, finite, literal, minus, unequal, whole

# doubles a literal must carry exactly: both zeros, the smallest subnormal, a value with an
# exponent, one no binary fraction holds, the largest finite, and the infinities
EXACT = [0.0, -0.0, 5e-324, 1e-05, 0.1, 0.3, -2.5, 1.7976931348623157e308, math.inf, -math.inf]


def _bits(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", value))[0]


def test_a_literal_is_the_doubles_bit_pattern_in_three_fields() -> None:
    # sign, eleven exponent bits biased by 1023, and the fraction's fifty-two
    assert literal(1.0) == f"(fp #b0 #b01111111111 #b{'0' * 52})"
    assert literal(-2.0) == f"(fp #b1 #b10000000000 #b{'0' * 52})"


@pytest.mark.parametrize("value", EXACT, ids=[repr(value) for value in EXACT])
def test_a_literal_reads_back_as_the_same_double(value: float) -> None:
    # bit for bit, so -0.0 does not come back as 0.0
    assert _bits(decode(literal(value))) == _bits(value)


def test_nan_reads_back_as_a_nan() -> None:
    assert math.isnan(decode(literal(math.nan)))


def test_nan_is_written_as_the_quiet_nan_python_holds() -> None:
    assert literal(math.nan) == f"(fp #b0 #b11111111111 #b1{'0' * 51})"


@pytest.mark.parametrize(
    "text",
    [
        "(fp #b0 #b1 #b0)",
        f"(fp #b2 #b{'0' * 11} #b{'0' * 52})",
        f"(fp #b0 #b{'0' * 11} #b{'0' * 52}",
        "(_ NaN 11 53)",
        "1.5",
    ],
)
def test_a_value_that_is_not_a_double_in_three_fields_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match="double"):
        decode(text)


def test_finite_rules_out_nan_and_both_infinities() -> None:
    assert finite("x") == "(not (or (fp.isNaN x) (fp.isInfinite x)))"


def test_unequal_is_ieee_inequality() -> None:
    # SMT-LIB's `distinct` tells -0.0 from 0.0 and calls NaN equal to itself
    assert unequal("x", "y") == "(not (fp.eq x y))"


def test_minus_negates_one_operand_and_subtracts_two() -> None:
    assert minus("x") == "(fp.neg x)"
    assert minus("x", "y") == "(fp.sub RNE x y)"


def test_whole_is_a_finite_value_its_integral_part_equals() -> None:
    assert whole("x") == "(and (not (fp.isInfinite x)) (fp.eq (fp.roundToIntegral RTZ x) x))"
