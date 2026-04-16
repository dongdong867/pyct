"""URL routing benchmark target.

Category: String parsing with hierarchical dispatch
Intent: Route a URL to a handler based on protocol, host, path segments, query params,
    and fragment identifiers.
Challenge: Layered string splitting — protocol extraction, host/path separation, segment
    matching for versioned APIs, admin routes, static content, health checks, and auth
    endpoints — forces engines to reason about multiple levels of string decomposition.
"""

from __future__ import annotations

MAX_URL_LENGTH = 2048


def _extract_protocol(url: str) -> tuple[str, str]:
    """Split protocol from the rest of the URL. Returns (protocol, remainder)."""
    if "://" not in url:
        return "", url
    protocol, remainder = url.split("://", maxsplit=1)
    return protocol.lower(), remainder


def _split_host_path(remainder: str) -> tuple[str, str]:
    """Split host from path. Returns (host, path)."""
    if "/" not in remainder:
        return remainder, "/"
    idx = remainder.index("/")
    return remainder[:idx], remainder[idx:]


def _route_api(segments: list[str]) -> str:
    """Route /api/v[N]/... paths."""
    if len(segments) < 2:
        return "api_root"
    version_seg = segments[1]
    if not version_seg.startswith("v") or not version_seg[1:].isdigit():
        return "api_invalid_version"
    if len(segments) < 3:
        return "api_versioned_root"
    resource = segments[2]
    if resource == "users":
        return "api_users"
    if resource == "products":
        return "api_products"
    if resource == "orders":
        return "api_orders"
    return "api_unknown_resource"


def _route_admin(segments: list[str]) -> str:
    """Route /admin/... paths."""
    if len(segments) < 2:
        return "admin_dashboard"
    sub = segments[1]
    if sub == "users":
        return "admin_users"
    if sub == "settings":
        return "admin_settings"
    return "admin_unknown"


def _route_auth(segments: list[str]) -> str:
    """Route /auth/... paths."""
    if len(segments) < 2:
        return "auth_root"
    action = segments[1]
    if action == "login":
        return "auth_login"
    if action == "logout":
        return "auth_logout"
    if action == "callback":
        return "auth_callback"
    return "auth_unknown"


def _route_path(path: str) -> str:
    """Dispatch based on the first path segment."""
    segments = [s for s in path.split("/") if s]
    if len(segments) == 0:
        return "root"
    first = segments[0]
    if first == "api":
        return _route_api(segments)
    if first == "admin":
        return _route_admin(segments)
    if first in ("public", "static"):
        return "static_content"
    if first in ("health", "status"):
        return "health_check"
    if first == "auth":
        return _route_auth(segments)
    return "not_found"


def url_routing(url: str) -> str:
    """Route a URL and return a string classification of the matched handler."""
    if len(url) == 0:
        return "empty_url"
    if len(url) > MAX_URL_LENGTH:
        return "url_too_long"

    protocol, remainder = _extract_protocol(url)
    if protocol != "" and protocol not in ("http", "https"):
        return "unsupported_protocol"

    host, full_path = _split_host_path(remainder)
    if len(host) == 0:
        return "missing_host"
    if "." not in host:
        return "invalid_host_no_dots"

    has_fragment = "#" in full_path
    path_no_fragment = full_path.split("#", maxsplit=1)[0]
    has_query = "?" in path_no_fragment
    path = path_no_fragment.split("?", maxsplit=1)[0]

    route = _route_path(path)

    if has_query and has_fragment:
        return route + "_with_params_and_fragment"
    if has_query:
        return route + "_with_params"
    if has_fragment:
        return route + "_with_fragment"
    return route
