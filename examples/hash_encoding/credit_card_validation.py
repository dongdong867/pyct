"""Credit card validation benchmark target.

Category: Numeric string validation with checksum verification
Intent: Validate credit card numbers by stripping formatting, checking length,
    detecting card type by prefix, and verifying the Luhn checksum.
Challenge: Prefix matching creates overlapping numeric ranges (Visa 4*, MC 51-55*,
    Amex 34/37*, Discover 6011*), and the Luhn checksum introduces an arithmetic
    constraint that concolic engines must solve alongside string/length conditions.
"""

from __future__ import annotations

MIN_CARD_LENGTH = 13
MAX_CARD_LENGTH = 19


def _strip_formatting(number: str) -> str:
    """Remove spaces and dashes from the card number."""
    return number.replace(" ", "").replace("-", "")


def _luhn_checksum(digits: str) -> bool:
    """Verify a digit string passes the Luhn algorithm."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _detect_visa(stripped: str) -> str | None:
    """Check for Visa card (starts with 4, length 13 or 16)."""
    if not stripped.startswith("4"):
        return None
    if len(stripped) == 16:
        return "visa"
    if len(stripped) == 13:
        return "visa_legacy"
    return "visa_invalid_length"


def _detect_mastercard(stripped: str) -> str | None:
    """Check for Mastercard (starts with 51-55, length 16)."""
    if len(stripped) < 2:
        return None
    prefix2 = int(stripped[:2])
    if prefix2 < 51 or prefix2 > 55:
        return None
    if len(stripped) == 16:
        return "mastercard"
    return "mastercard_invalid_length"


def _detect_amex(stripped: str) -> str | None:
    """Check for American Express (starts with 34 or 37, length 15)."""
    if not stripped.startswith("34") and not stripped.startswith("37"):
        return None
    if len(stripped) == 15:
        return "amex"
    return "amex_invalid_length"


def _detect_discover(stripped: str) -> str | None:
    """Check for Discover (starts with 6011, length 16)."""
    if not stripped.startswith("6011"):
        return None
    if len(stripped) == 16:
        return "discover"
    return "discover_invalid_length"


def _detect_card_type(stripped: str) -> str:
    """Identify card type by prefix and length."""
    visa = _detect_visa(stripped)
    if visa is not None:
        return visa
    mastercard = _detect_mastercard(stripped)
    if mastercard is not None:
        return mastercard
    amex = _detect_amex(stripped)
    if amex is not None:
        return amex
    discover = _detect_discover(stripped)
    if discover is not None:
        return discover
    return "unknown_issuer"


def credit_card_validation(number: str) -> str:
    """Validate a credit card number and return type classification."""
    if len(number) == 0:
        return "invalid_empty"

    stripped = _strip_formatting(number)

    if not stripped.isdigit():
        return "invalid_non_digit"
    if len(stripped) < MIN_CARD_LENGTH:
        return "invalid_too_short"
    if len(stripped) > MAX_CARD_LENGTH:
        return "invalid_too_long"

    card_type = _detect_card_type(stripped)
    if card_type.endswith("_invalid_length"):
        return card_type
    if card_type == "unknown_issuer":
        return "unknown_issuer"

    if not _luhn_checksum(stripped):
        return f"{card_type}_invalid_checksum"

    return f"{card_type}_valid"
