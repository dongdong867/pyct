"""HTTP request classification by method, path, and payload size.

Category: mixed_type_synergy
Intent: Classify an incoming HTTP request into a semantic category based on
    the interaction of method (string), URL path prefix (string), and
    content-length (integer).  Guards reject invalid methods and negative
    content lengths.
Challenge: ~20 branches arise from the cross-product of five valid methods,
    five path prefixes, and payload-size constraints.  The concolic tester
    must coordinate string-prefix checks with integer range constraints and
    method-specific rules to reach every classification.
"""

from __future__ import annotations

_VALID_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})
_MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def http_request_classification(
    method: str,
    path: str,
    content_length: int,
) -> str:
    """Classify an HTTP request into a semantic category."""
    if method not in _VALID_METHODS:
        return "invalid_method"

    if content_length < 0:
        return "invalid_content_length"

    body_check = _check_body_constraints(method, content_length)
    if body_check is not None:
        return body_check

    return _classify_by_path(method, path, content_length)


def _check_body_constraints(method: str, content_length: int) -> str | None:
    if method == "GET" and content_length > 0:
        return "get_with_body"

    if method in ("POST", "PUT") and content_length == 0:
        return "missing_body"

    if content_length > _MAX_PAYLOAD_BYTES:
        return "payload_too_large"

    return None


def _classify_by_path(method: str, path: str, content_length: int) -> str:
    if path.startswith("/upload/"):
        return _classify_upload(method, content_length)

    if path.startswith("/webhook/"):
        return _classify_webhook(method)

    if path.startswith("/api/"):
        return _classify_api(method)

    if path.startswith("/admin/"):
        return _classify_api(method)

    return "static_request"


def _classify_upload(method: str, content_length: int) -> str:
    if method != "POST":
        return "upload_method_not_allowed"
    if content_length == 0:
        return "missing_body"
    return "upload_request"


def _classify_webhook(method: str) -> str:
    if method != "POST":
        return "webhook_method_not_allowed"
    return "webhook_request"


def _classify_api(method: str) -> str:
    if method == "GET":
        return "read_request"
    if method == "DELETE":
        return "delete_request"
    return "write_request"
