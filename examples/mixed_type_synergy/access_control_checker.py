"""Role-based access control checker with trust-level modifiers.

Category: mixed_type_synergy
Intent: Decide whether a role (string) may access a resource path (string) at
    a given trust level (integer).  Trust level acts as a secondary gate that
    can deny otherwise-permitted access or escalate limited roles.
Challenge: ~18 branches emerge from the matrix of four roles, five resource
    prefixes, and trust-level thresholds.  The concolic tester must coordinate
    string-equality and string-prefix constraints with integer range checks to
    cover every access decision.
"""

from __future__ import annotations

_VALID_ROLES = frozenset({"admin", "editor", "viewer", "guest"})
_RESOURCE_PREFIXES = ("/users/", "/admin/", "/public/", "/api/", "/internal/")
_TRUST_MIN = 0
_TRUST_MAX = 100
_LOW_TRUST_THRESHOLD = 20
_HIGH_TRUST_THRESHOLD = 80


def access_control_checker(role: str, resource: str, trust_level: int) -> str:
    """Return an access decision for *role* requesting *resource*."""
    if role not in _VALID_ROLES:
        return "invalid_role"

    if not _has_valid_prefix(resource):
        return "invalid_resource"

    if trust_level < _TRUST_MIN or trust_level > _TRUST_MAX:
        return "invalid_trust_level"

    if trust_level < _LOW_TRUST_THRESHOLD:
        return "denied_low_trust"

    return _decide(role, resource, trust_level)


def _has_valid_prefix(resource: str) -> bool:
    return any(resource.startswith(p) for p in _RESOURCE_PREFIXES)


def _decide(role: str, resource: str, trust_level: int) -> str:
    if role == "admin":
        return "full_access"

    if role == "editor":
        return _editor_access(resource)

    if role == "viewer":
        return _viewer_access(resource, trust_level)

    # guest
    return _guest_access(resource)


def _editor_access(resource: str) -> str:
    if resource.startswith("/admin/") or resource.startswith("/internal/"):
        return "denied_insufficient_role"
    return "edit_access"


def _viewer_access(resource: str, trust_level: int) -> str:
    if resource.startswith("/admin/") or resource.startswith("/internal/"):
        return "denied_insufficient_role"

    if resource.startswith("/users/"):
        return "denied_insufficient_role"

    if resource.startswith("/api/") and trust_level > _HIGH_TRUST_THRESHOLD:
        return "escalated_read_access"

    if resource.startswith("/api/"):
        return "denied_insufficient_role"

    return "read_only_access"


def _guest_access(resource: str) -> str:
    if resource.startswith("/public/"):
        return "public_read_access"
    return "denied_guest"
