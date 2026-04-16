"""Email validation benchmark target.

Category: String parsing and pattern matching
Intent: Validate email addresses against RFC-inspired format rules including local part
    constraints, domain structure, TLD validation, and disposable domain detection.
Challenge: Many interleaving string conditions — local/domain split, dot placement,
    length limits, character restrictions, TLD categories, and disposable domain checks
    create a deep decision tree that concolic engines must navigate precisely.
"""

from __future__ import annotations

DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "throwaway.email",
        "yopmail.com",
    }
)

GENERIC_TLDS = frozenset({"com", "org", "net"})
RESTRICTED_TLDS = frozenset({"edu", "gov", "mil"})
MODERN_TLDS = frozenset({"io", "dev", "app", "ai"})
COUNTRY_TLDS = frozenset({"uk", "de", "jp", "fr", "cn"})

MAX_EMAIL_LENGTH = 254
MAX_LOCAL_LENGTH = 64
MAX_DOMAIN_PART_LENGTH = 63


def _check_local_part(local: str) -> str | None:
    """Return an error classification if the local part is invalid, else None."""
    if len(local) == 0:
        return "invalid_empty_local"
    if len(local) > MAX_LOCAL_LENGTH:
        return "invalid_local_too_long"
    if local.startswith(".") or local.endswith("."):
        return "invalid_local_dot_boundary"
    if ".." in local:
        return "invalid_local_consecutive_dots"
    return None


def _check_domain_parts(domain: str) -> str | None:
    """Return an error classification if the domain structure is invalid, else None."""
    if "." not in domain:
        return "invalid_no_tld"
    parts = domain.split(".")
    for part in parts:
        if len(part) == 0:
            return "invalid_empty_domain_part"
        if len(part) > MAX_DOMAIN_PART_LENGTH:
            return "invalid_domain_part_too_long"
    return None


def _classify_tld(tld: str) -> str | None:
    """Return TLD category or error classification."""
    if len(tld) < 2:
        return "invalid_tld_too_short"
    if not tld.isalpha():
        return "invalid_tld_not_alpha"
    lower_tld = tld.lower()
    if lower_tld in GENERIC_TLDS:
        return "generic_tld"
    if lower_tld in RESTRICTED_TLDS:
        return "restricted_tld"
    if lower_tld in MODERN_TLDS:
        return "modern_tld"
    if lower_tld in COUNTRY_TLDS:
        return "country_tld"
    return "unknown_tld"


def email_validation(email: str) -> str:
    """Validate an email address and return a string classification."""
    if len(email) == 0:
        return "invalid_empty"
    if len(email) > MAX_EMAIL_LENGTH:
        return "invalid_too_long"

    at_count = email.count("@")
    if at_count == 0:
        return "missing_at"
    if at_count > 1:
        return "multiple_at"

    local, domain = email.split("@", maxsplit=1)

    local_error = _check_local_part(local)
    if local_error is not None:
        return local_error

    domain_error = _check_domain_parts(domain)
    if domain_error is not None:
        return domain_error

    tld = domain.rsplit(".", maxsplit=1)[1]
    tld_result = _classify_tld(tld)
    if tld_result is not None and tld_result.startswith("invalid_"):
        return tld_result

    if domain.lower() in DISPOSABLE_DOMAINS:
        return "disposable_domain"

    if tld_result is None:
        return "valid_unknown_tld"
    return f"valid_{tld_result}"
