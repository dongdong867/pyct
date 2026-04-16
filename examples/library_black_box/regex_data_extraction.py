"""Regex-based data extraction benchmark target.

Category: Pattern matching with multiple regex paths
Intent: Detect and classify embedded structured data (phone, email, date, IP, UUID)
    within a free-form text string, returning the first match type found.
Challenge: Five independent regex searches create a combinatorial space of match/no-match
    outcomes. The solver must craft inputs that selectively trigger each pattern while
    avoiding others, or fall through to text-type classification.
"""

from __future__ import annotations

import re

_PHONE_DASH = re.compile(r"\d{3}-\d{3}-\d{4}")
_PHONE_PAREN = re.compile(r"\(\d{3}\)\s?\d{3}-\d{4}")

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_DATE_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_US = re.compile(r"\d{2}/\d{2}/\d{4}")

_IPV4_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")

_UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _detect_phone(text: str) -> str | None:
    """Return classification if a phone number pattern is found."""
    if _PHONE_PAREN.search(text) is not None:
        return "phone_parenthesized"
    if _PHONE_DASH.search(text) is not None:
        return "phone_dashed"
    return None


def _detect_email(text: str) -> str | None:
    """Return classification if an email pattern is found."""
    if _EMAIL_PATTERN.search(text) is None:
        return None
    return "email_detected"


def _detect_date(text: str) -> str | None:
    """Return classification if a date pattern is found (ISO or US format)."""
    if _DATE_ISO.search(text) is not None:
        return "date_iso_detected"
    if _DATE_US.search(text) is not None:
        return "date_us_detected"
    return None


def _detect_ipv4(text: str) -> str | None:
    """Return classification if an IPv4 address pattern is found."""
    match = _IPV4_PATTERN.search(text)
    if match is None:
        return None
    octets = match.group().split(".")
    for octet in octets:
        if int(octet) > 255:
            return "ip_invalid_octet"
    return "ip_detected"


def _detect_uuid(text: str) -> str | None:
    """Return classification if a UUID pattern is found."""
    if _UUID_PATTERN.search(text) is None:
        return None
    return "uuid_detected"


def _classify_fallback(text: str) -> str:
    """Classify text that matched no structured pattern."""
    if text.strip().isdigit():
        return "numeric_only"
    if len(text.strip()) == 0:
        return "empty_content"
    return "plain_text"


def regex_data_extraction(text: str) -> str:
    """Detect and classify the first embedded structured data type in free-form text."""
    if len(text) == 0:
        return "empty_input"

    phone = _detect_phone(text)
    if phone is not None:
        return phone

    email = _detect_email(text)
    if email is not None:
        return email

    date = _detect_date(text)
    if date is not None:
        return date

    ip = _detect_ipv4(text)
    if ip is not None:
        return ip

    uuid = _detect_uuid(text)
    if uuid is not None:
        return uuid

    return _classify_fallback(text)
