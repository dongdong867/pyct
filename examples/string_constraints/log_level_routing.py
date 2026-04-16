"""Log level routing benchmark target.

Category: Multi-format string detection and classification
Intent: Detect log format (JSON, syslog, CSV, plain text) and route by severity level
    with format-specific prefixing.
Challenge: The engine must explore four mutually-exclusive format-detection paths, each
    with its own parsing logic and severity mapping, making it hard to reach all
    format x severity combinations without precise input construction.
"""

from __future__ import annotations

import json
import re

_SYSLOG_PATTERN = re.compile(r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+(\w+)")

SEVERITY_ORDER = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

SEVERITY_SET = frozenset(SEVERITY_ORDER)

MIN_LOG_LENGTH = 3


def _classify_severity(level: str) -> str:
    """Map a severity string to a routing classification."""
    normalized = level.upper()
    if normalized in ("CRITICAL", "FATAL"):
        return "route_critical"
    if normalized == "ERROR":
        return "route_error"
    if normalized in ("WARN", "WARNING"):
        return "route_warning"
    if normalized == "INFO":
        return "route_info"
    if normalized == "DEBUG":
        return "route_debug"
    return "route_unknown_level"


def _try_json_format(log_line: str) -> str | None:
    """Attempt to parse as JSON log. Returns classification or None."""
    if not log_line.startswith("{"):
        return None
    try:
        data = json.loads(log_line)
    except (json.JSONDecodeError, ValueError):
        return "json_malformed"
    if not isinstance(data, dict):
        return "json_not_object"
    level = data.get("level")
    if level is None:
        return "json_missing_level"
    if not isinstance(level, str):
        return "json_invalid_level_type"
    return "json_" + _classify_severity(level)


def _try_syslog_format(log_line: str) -> str | None:
    """Attempt to parse as syslog format. Returns classification or None."""
    match = _SYSLOG_PATTERN.match(log_line)
    if match is None:
        return None
    level = match.group(1)
    return "syslog_" + _classify_severity(level)


def _try_csv_format(log_line: str) -> str | None:
    """Attempt to parse as CSV log (timestamp,level,message). Returns classification or None."""
    if "," not in log_line:
        return None
    fields = log_line.split(",")
    if len(fields) < 3:
        return None
    level_field = fields[1].strip()
    if level_field.upper() not in SEVERITY_SET:
        return None
    return "csv_" + _classify_severity(level_field)


def _classify_plain_text(log_line: str) -> str:
    """Fall back to plain-text keyword scanning, highest severity first."""
    upper = log_line.upper()
    for severity in reversed(SEVERITY_ORDER):
        if severity in upper:
            return "text_" + _classify_severity(severity)
    if "WARN" in upper:
        return "text_route_warning"
    return "text_route_unclassified"


def log_level_routing(log_line: str) -> str:
    """Detect log format and route by severity level."""
    if len(log_line) == 0:
        return "empty_input"
    if len(log_line) < MIN_LOG_LENGTH:
        return "input_too_short"

    json_result = _try_json_format(log_line)
    if json_result is not None:
        return json_result

    syslog_result = _try_syslog_format(log_line)
    if syslog_result is not None:
        return syslog_result

    csv_result = _try_csv_format(log_line)
    if csv_result is not None:
        return csv_result

    return _classify_plain_text(log_line)
