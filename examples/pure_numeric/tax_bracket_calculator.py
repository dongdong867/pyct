"""Progressive tax bracket calculator.

Category: pure_numeric
Intent: Determine which marginal tax bracket an integer income falls into,
    parameterised by filing status (single vs. married-filing-jointly).
Challenge: The function has ~15 branches created by a cascade of numeric
    threshold comparisons whose boundaries shift depending on a string
    parameter.  A concolic tester must coordinate string equality with
    range-based integer constraints to cover every bracket.
"""

from __future__ import annotations

_SINGLE_BRACKETS: list[tuple[int, str]] = [
    (500_000, "bracket_37"),
    (200_000, "bracket_35"),
    (160_000, "bracket_32"),
    (85_000, "bracket_24"),
    (40_000, "bracket_22"),
    (10_000, "bracket_12"),
    (0, "bracket_10"),
]

_MARRIED_SCALE = 2


def tax_bracket_calculator(income: int, filing_status: str) -> str:
    """Return the marginal tax-bracket label for *income* and *filing_status*.

    ``filing_status`` must be ``"single"`` or ``"married"``.
    """
    if filing_status not in ("single", "married"):
        return "invalid_status"

    if income < 0:
        return "negative_income"

    if income == 0:
        return "no_tax"

    multiplier = _MARRIED_SCALE if filing_status == "married" else 1
    return _bracket_for_income(income, multiplier)


def _bracket_for_income(income: int, multiplier: int) -> str:
    for threshold, label in _SINGLE_BRACKETS:
        if income > threshold * multiplier:
            return label
    # Unreachable when brackets are well-formed, but keeps the function total.
    return "bracket_10"
