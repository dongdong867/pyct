"""Real-world test suite — external library functions.

22 functions from 6 open-source Python libraries, imported directly from
installed packages. Library versions pinned in pyproject.toml
[project.optional-dependencies].realworld.
"""

from __future__ import annotations

from tools.benchmark.targets import BenchmarkTarget

REALWORLD_SUITE: list[BenchmarkTarget] = [
    # --- werkzeug: HTTP header parsing (6 functions) ---
    BenchmarkTarget(
        name="Parse Options Header",
        module="werkzeug.http",
        function="parse_options_header",
        initial_args={"value": "text/html; charset=utf-8; boundary=something"},
        category="werkzeug",
        description="HTTP options header — semicolon-separated key=value pairs",
    ),
    BenchmarkTarget(
        name="Parse Range Header",
        module="werkzeug.http",
        function="parse_range_header",
        initial_args={"value": "bytes=0-499, 500-999"},
        category="werkzeug",
        description="HTTP Range header — byte range parsing with validation",
    ),
    BenchmarkTarget(
        name="Parse Content Range Header",
        module="werkzeug.http",
        function="parse_content_range_header",
        initial_args={"value": "bytes 0-499/1234"},
        category="werkzeug",
        description="HTTP Content-Range — start/end/total extraction",
    ),
    BenchmarkTarget(
        name="Parse Dict Header",
        module="werkzeug.http",
        function="parse_dict_header",
        initial_args={"value": 'realm="test", nonce="abc123", qop="auth"'},
        category="werkzeug",
        description="HTTP dict header — quoted value parsing and unescaping",
    ),
    BenchmarkTarget(
        name="Parse List Header",
        module="werkzeug.http",
        function="parse_list_header",
        initial_args={"value": "text/html, application/json, text/plain"},
        category="werkzeug",
        description="HTTP list header — comma-separated items with quoting",
    ),
    BenchmarkTarget(
        name="Parse Cookie",
        module="werkzeug.http",
        function="parse_cookie",
        initial_args={"header": "session=abc123; theme=dark; lang=en"},
        category="werkzeug",
        description="HTTP Cookie header — key=value pairs with special chars",
    ),
    # --- validators: input format validation (8 functions) ---
    BenchmarkTarget(
        name="Validate URL",
        module="validators.url",
        function="url",
        initial_args={"value": "https://example.com/path?query=1#frag"},
        category="validators",
        description="Full URL validation — scheme, host, port, path, query, fragment",
    ),
    BenchmarkTarget(
        name="Validate Email",
        module="validators.email",
        function="email",
        initial_args={"value": "user@example.com"},
        category="validators",
        description="Email address validation — local part, domain, quoted strings",
    ),
    BenchmarkTarget(
        name="Validate Hostname",
        module="validators.hostname",
        function="hostname",
        initial_args={"value": "sub.example.com:8080"},
        category="validators",
        description="Hostname validation — labels, TLD, optional port",
    ),
    BenchmarkTarget(
        name="Validate Domain",
        module="validators.domain",
        function="domain",
        initial_args={"value": "example.co.uk"},
        category="validators",
        description="Domain name validation — label length, TLD rules",
    ),
    BenchmarkTarget(
        name="Validate Russian INN",
        module="validators.i18n.ru",
        function="ru_inn",
        initial_args={"value": "7707083893"},
        category="validators",
        description="Russian taxpayer ID — digit check with control sum",
    ),
    BenchmarkTarget(
        name="Validate French SSN",
        module="validators.i18n.fr",
        function="fr_ssn",
        initial_args={"value": "2840845113794"},
        category="validators",
        description="French social security number — gender, year, dept, commune",
    ),
    BenchmarkTarget(
        name="Validate IPv4",
        module="validators.ip_address",
        function="ipv4",
        initial_args={"value": "192.168.1.1"},
        category="validators",
        description="IPv4 address validation — octet ranges, CIDR notation",
    ),
    BenchmarkTarget(
        name="Validate Country Code",
        module="validators.country",
        function="country_code",
        initial_args={"value": "US"},
        category="validators",
        description="ISO country code — alpha-2, alpha-3, numeric formats",
    ),
    # --- phonenumbers: phone number parsing (2 functions) ---
    BenchmarkTarget(
        name="Parse Phone Number",
        module="phonenumbers.phonenumberutil",
        function="parse",
        initial_args={"number": "+1 650 253 0000", "region": "US"},
        category="phonenumbers",
        description="International phone number parsing — country code, national number",
    ),
    BenchmarkTarget(
        name="Is Possible Number String",
        module="phonenumbers.phonenumberutil",
        function="is_possible_number_string",
        initial_args={"number": "+1 650 253 0000", "region_dialing_from": "US"},
        category="phonenumbers",
        description="Quick phone number plausibility check — length-based validation",
    ),
    # --- urllib.parse: URL processing (4 functions, stdlib) ---
    BenchmarkTarget(
        name="URL Split",
        module="urllib.parse",
        function="urlsplit",
        initial_args={"url": "https://user:pass@example.com:8080/path?q=1#frag"},
        category="urllib_parse",
        description="Decompose URL into scheme, netloc, path, query, fragment",
    ),
    BenchmarkTarget(
        name="URL Quote",
        module="urllib.parse",
        function="quote",
        initial_args={"string": "hello world/foo&bar=baz"},
        category="urllib_parse",
        description="Percent-encode URL component — safe char handling",
    ),
    BenchmarkTarget(
        name="URL Encode",
        module="urllib.parse",
        function="urlencode",
        initial_args={"query": {"key": "value", "name": "test param", "special": "&="}},
        category="urllib_parse",
        description="Dict-to-query-string — non-primitive input, LLM seeding showcase",
    ),
    BenchmarkTarget(
        name="Parse Query String",
        module="urllib.parse",
        function="parse_qs",
        initial_args={"qs": "key=value&name=test&key=other&empty="},
        category="urllib_parse",
        description="Query string to dict — multi-value keys, blank handling",
    ),
    # --- simplejson: JSON parsing (1 function) ---
    BenchmarkTarget(
        name="JSON Loads",
        module="simplejson",
        function="loads",
        initial_args={"s": '{"key": "value", "num": 42, "nested": {"a": true}}'},
        category="simplejson",
        description="JSON string to Python object — tokenizer, decoder dispatch",
    ),
    # --- python-dateutil: date parsing (1 function) ---
    BenchmarkTarget(
        name="Parse Date String",
        module="dateutil.parser._parser",
        function="parse",
        initial_args={"timestr": "2024-06-15 14:30:00"},
        category="dateutil",
        description="Fuzzy date/time string parsing — many format heuristics",
    ),
]
