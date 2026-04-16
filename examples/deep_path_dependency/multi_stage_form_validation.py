"""Multi-stage form validation benchmark target.

Category: Deep path dependency — sequential stage validation with cascading gates
Intent: Validate a pipe-delimited form string through four sequential stages
Challenge: Each validation stage is only reachable if ALL prior stages passed.
    To reach the final age-group classification, the solver must simultaneously satisfy
    name constraints (length, no digits), email format ('@' and '.' placement),
    age range (numeric, 18-120), and address requirements (length, contains digit).
    This creates a 4-deep dependency chain that demands precise multi-field coordination.
"""

from __future__ import annotations


def _validate_name(name: str) -> str | None:
    """Return error classification if name is invalid, else None."""
    if len(name) == 0:
        return "invalid_name_empty"
    if len(name) < 2 or len(name) > 50:
        return "invalid_name_length"
    for ch in name:
        if ch.isdigit():
            return "invalid_name_has_digit"
    return None


def _validate_email(email: str) -> str | None:
    """Return error classification if email is invalid, else None."""
    if len(email) == 0:
        return "invalid_email_empty"
    at_pos = email.find("@")
    if at_pos < 0:
        return "invalid_email_no_at"
    after_at = email[at_pos + 1 :]
    if "." not in after_at:
        return "invalid_email_no_dot"
    return None


def _validate_age(age_str: str) -> tuple[str | None, int]:
    """Return (error classification or None, parsed age)."""
    if len(age_str) == 0 or not age_str.isdigit():
        return "invalid_age_not_numeric", 0
    age = int(age_str)
    if age < 18:
        return "invalid_age_under_18", age
    if age > 120:
        return "invalid_age_over_120", age
    return None, age


def _validate_address(address: str) -> str | None:
    """Return error classification if address is invalid, else None."""
    if len(address) == 0:
        return "invalid_address_empty"
    if len(address) < 10:
        return "invalid_address_too_short"
    has_digit = False
    for ch in address:
        if ch.isdigit():
            has_digit = True
            break
    if not has_digit:
        return "invalid_address_no_number"
    return None


def _classify_age_group(age: int) -> str:
    """Return age group classification."""
    if age <= 25:
        return "young_adult"
    if age <= 59:
        return "adult"
    return "senior"


def multi_stage_form_validation(form_data: str) -> str:
    """Validate pipe-delimited form stages and return a string classification."""
    if len(form_data) == 0:
        return "empty_form"

    stages = form_data.split("|")
    if len(stages) != 4:
        return "invalid_stage_count"

    name_error = _validate_name(stages[0])
    if name_error is not None:
        return name_error

    email_error = _validate_email(stages[1])
    if email_error is not None:
        return email_error

    age_error, age = _validate_age(stages[2])
    if age_error is not None:
        return age_error

    address_error = _validate_address(stages[3])
    if address_error is not None:
        return address_error

    return _classify_age_group(age)
