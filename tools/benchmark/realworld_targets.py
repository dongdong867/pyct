"""Real-world test suite — external library functions.

22 functions from 6 open-source Python libraries, imported directly from
installed packages. Library versions pinned in pyproject.toml
[project.optional-dependencies].realworld.

Coverage uses entered-scope analysis: the denominator is lines in
functions that were actually entered (transitively called), not just
the entry function or the entire package.
"""

from __future__ import annotations

import importlib
import logging
import os

from tools.benchmark.targets import BenchmarkTarget

log = logging.getLogger("benchmark.realworld")


def _resolve_source_path(package_name: str) -> str | None:
    """Find the installed package's source directory."""
    try:
        module = importlib.import_module(package_name)
    except ImportError:
        return None
    init_file = getattr(module, "__file__", None)
    if init_file is None:
        return None
    return os.path.dirname(os.path.abspath(init_file))


def _build_realworld_suite() -> list[BenchmarkTarget]:
    """Build realworld suite with resolved source_path per package."""
    source_paths: dict[str, str | None] = {}
    targets: list[BenchmarkTarget] = []

    for t in _RAW_TARGETS:
        pkg = t["package"]
        if pkg not in source_paths:
            source_paths[pkg] = _resolve_source_path(pkg)
        sp = source_paths[pkg]
        if sp is None:
            log.warning("Skipping %s: package %s not installed", t["name"], pkg)
            continue
        targets.append(
            BenchmarkTarget(
                name=t["name"],
                module=t["module"],
                function=t["function"],
                initial_args=t["initial_args"],
                category=t["category"],
                description=t["description"],
                source_path=sp,
            )
        )
    return targets


_RAW_TARGETS: list[dict] = [
    # --- werkzeug: HTTP header parsing (6 functions) ---
    {
        "name": "Parse Options Header",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_options_header",
        "initial_args": {"value": "text/html; charset=utf-8; boundary=something"},
        "category": "werkzeug",
        "description": "HTTP options header — semicolon-separated key=value pairs",
    },
    {
        "name": "Parse Range Header",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_range_header",
        "initial_args": {"value": "bytes=0-499, 500-999"},
        "category": "werkzeug",
        "description": "HTTP Range header — byte range parsing with validation",
    },
    {
        "name": "Parse Content Range Header",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_content_range_header",
        "initial_args": {"value": "bytes 0-499/1234"},
        "category": "werkzeug",
        "description": "HTTP Content-Range — start/end/total extraction",
    },
    {
        "name": "Parse Dict Header",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_dict_header",
        "initial_args": {"value": 'realm="test", nonce="abc123", qop="auth"'},
        "category": "werkzeug",
        "description": "HTTP dict header — quoted value parsing and unescaping",
    },
    {
        "name": "Parse List Header",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_list_header",
        "initial_args": {"value": "text/html, application/json, text/plain"},
        "category": "werkzeug",
        "description": "HTTP list header — comma-separated items with quoting",
    },
    {
        "name": "Parse Cookie",
        "package": "werkzeug",
        "module": "werkzeug.http",
        "function": "parse_cookie",
        "initial_args": {"header": "session=abc123; theme=dark; lang=en"},
        "category": "werkzeug",
        "description": "HTTP Cookie header — key=value pairs with special chars",
    },
    # --- validators: input format validation (8 functions) ---
    {
        "name": "Validate URL",
        "package": "validators",
        "module": "validators.url",
        "function": "url",
        "initial_args": {"value": "https://example.com/path?query=1#frag"},
        "category": "validators",
        "description": "Full URL validation — scheme, host, port, path, query, fragment",
    },
    {
        "name": "Validate Email",
        "package": "validators",
        "module": "validators.email",
        "function": "email",
        "initial_args": {"value": "user@example.com"},
        "category": "validators",
        "description": "Email address validation — local part, domain, quoted strings",
    },
    {
        "name": "Validate Hostname",
        "package": "validators",
        "module": "validators.hostname",
        "function": "hostname",
        "initial_args": {"value": "sub.example.com:8080"},
        "category": "validators",
        "description": "Hostname validation — labels, TLD, optional port",
    },
    {
        "name": "Validate Domain",
        "package": "validators",
        "module": "validators.domain",
        "function": "domain",
        "initial_args": {"value": "example.co.uk"},
        "category": "validators",
        "description": "Domain name validation — label length, TLD rules",
    },
    {
        "name": "Validate Russian INN",
        "package": "validators",
        "module": "validators.i18n.ru",
        "function": "ru_inn",
        "initial_args": {"value": "7707083893"},
        "category": "validators",
        "description": "Russian taxpayer ID — digit check with control sum",
    },
    {
        "name": "Validate French SSN",
        "package": "validators",
        "module": "validators.i18n.fr",
        "function": "fr_ssn",
        "initial_args": {"value": "2840845113794"},
        "category": "validators",
        "description": "French social security number — gender, year, dept, commune",
    },
    {
        "name": "Validate IPv4",
        "package": "validators",
        "module": "validators.ip_address",
        "function": "ipv4",
        "initial_args": {"value": "192.168.1.1"},
        "category": "validators",
        "description": "IPv4 address validation — octet ranges, CIDR notation",
    },
    {
        "name": "Validate Country Code",
        "package": "validators",
        "module": "validators.country",
        "function": "country_code",
        "initial_args": {"value": "US"},
        "category": "validators",
        "description": "ISO country code — alpha-2, alpha-3, numeric formats",
    },
    # --- phonenumbers: phone number parsing (2 functions) ---
    {
        "name": "Parse Phone Number",
        "package": "phonenumbers",
        "module": "phonenumbers.phonenumberutil",
        "function": "parse",
        "initial_args": {"number": "+1 650 253 0000", "region": "US"},
        "category": "phonenumbers",
        "description": "International phone number parsing — country code, national number",
    },
    {
        "name": "Is Possible Number String",
        "package": "phonenumbers",
        "module": "phonenumbers.phonenumberutil",
        "function": "is_possible_number_string",
        "initial_args": {"number": "+1 650 253 0000", "region_dialing_from": "US"},
        "category": "phonenumbers",
        "description": "Quick phone number plausibility check — length-based validation",
    },
    # --- urllib.parse: URL processing (4 functions, stdlib) ---
    {
        "name": "URL Split",
        "package": "urllib",
        "module": "urllib.parse",
        "function": "urlsplit",
        "initial_args": {"url": "https://user:pass@example.com:8080/path?q=1#frag"},
        "category": "urllib_parse",
        "description": "Decompose URL into scheme, netloc, path, query, fragment",
    },
    {
        "name": "URL Quote",
        "package": "urllib",
        "module": "urllib.parse",
        "function": "quote",
        "initial_args": {"string": "hello world/foo&bar=baz"},
        "category": "urllib_parse",
        "description": "Percent-encode URL component — safe char handling",
    },
    {
        "name": "URL Encode",
        "package": "urllib",
        "module": "urllib.parse",
        "function": "urlencode",
        "initial_args": {"query": {"key": "value", "name": "test param", "special": "&="}},
        "category": "urllib_parse",
        "description": "Dict-to-query-string — non-primitive input, LLM seeding showcase",
    },
    {
        "name": "Parse Query String",
        "package": "urllib",
        "module": "urllib.parse",
        "function": "parse_qs",
        "initial_args": {"qs": "key=value&name=test&key=other&empty="},
        "category": "urllib_parse",
        "description": "Query string to dict — multi-value keys, blank handling",
    },
    # --- simplejson: JSON parsing (1 function) ---
    {
        "name": "JSON Loads",
        "package": "simplejson",
        "module": "simplejson",
        "function": "loads",
        "initial_args": {"s": '{"key": "value", "num": 42, "nested": {"a": true}}'},
        "category": "simplejson",
        "description": "JSON string to Python object — tokenizer, decoder dispatch",
    },
    # --- python-dateutil: date parsing (1 function) ---
    {
        "name": "Parse Date String",
        "package": "dateutil",
        "module": "dateutil.parser._parser",
        "function": "parse",
        "initial_args": {"timestr": "2024-06-15 14:30:00"},
        "category": "dateutil",
        "description": "Fuzzy date/time string parsing — many format heuristics",
    },
]


REALWORLD_SUITE: list[BenchmarkTarget] = _build_realworld_suite()
