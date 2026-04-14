from __future__ import annotations


class SMTConstants:
    """Constants for SMT-LIB2 format conversion."""

    # Boolean literals
    TRUE = "true"
    FALSE = "false"

    # Numeric formatting
    NEGATIVE_PREFIX = "(- "
    NEGATIVE_SUFFIX = ")"

    # Unicode formatting
    UNICODE_PREFIX = "\\u{"
    UNICODE_SUFFIX = "}"

    # String escape mappings
    ESCAPE_MAPPINGS = {
        "\\": "\\\\",
        "\r": "\\r",
        "\n": "\\n",
        "\t": "\\t",
        '"': '""',
    }
