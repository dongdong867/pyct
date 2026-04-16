"""Nested configuration validator benchmark target.

Category: Complex structures — deeply nested dict validation
Intent: Validate a multi-level configuration dictionary with cross-field dependencies
Challenge: The solver must construct a dict with specific nested keys and value ranges,
    then satisfy cross-field constraints (e.g., high worker count requires pool_size).
    Each validation layer is only reachable if all prior layers pass, creating depth.
"""

from __future__ import annotations

VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

REQUIRED_TOP_KEYS = ("database", "server")


def _validate_database(database: object) -> str | None:
    """Return error classification if database section is invalid, else None."""
    if not isinstance(database, dict):
        return "invalid_database_type"
    host = database.get("host")
    if host is None or not isinstance(host, str) or len(host) == 0:
        return "invalid_database_host"
    port = database.get("port")
    if port is None or not isinstance(port, int):
        return "invalid_database_port_type"
    if port < 1 or port > 65535:
        return "invalid_database_port_range"
    name = database.get("name")
    if name is None or not isinstance(name, str) or len(name) == 0:
        return "invalid_database_name"
    return None


def _validate_server(server: object) -> str | None:
    """Return error classification if server section is invalid, else None."""
    if not isinstance(server, dict):
        return "invalid_server_type"
    host = server.get("host")
    if host is None or not isinstance(host, str) or len(host) == 0:
        return "invalid_server_host"
    port = server.get("port")
    if port is None or not isinstance(port, int):
        return "invalid_server_port_type"
    if port < 1 or port > 65535:
        return "invalid_server_port_range"
    workers = server.get("workers")
    if workers is None or not isinstance(workers, int):
        return "invalid_workers_type"
    if workers < 1 or workers > 32:
        return "invalid_workers_range"
    return None


def _validate_logging(logging_section: object) -> str | None:
    """Return error classification if logging section is invalid, else None."""
    if not isinstance(logging_section, dict):
        return "invalid_logging_type"
    level = logging_section.get("level")
    if level is not None and level not in VALID_LOG_LEVELS:
        return "invalid_log_level"
    file_path = logging_section.get("file")
    if file_path is not None:
        if not isinstance(file_path, str) or len(file_path) == 0:
            return "invalid_log_file"
    return None


def nested_config_validator(data: dict) -> str:
    """Validate a nested configuration dictionary and return a string classification."""
    if len(data) == 0:
        return "empty_config"

    for key in REQUIRED_TOP_KEYS:
        if key not in data:
            return "missing_" + key

    db_error = _validate_database(data["database"])
    if db_error is not None:
        return db_error

    server_error = _validate_server(data["server"])
    if server_error is not None:
        return server_error

    logging_section = data.get("logging")
    if logging_section is not None:
        log_error = _validate_logging(logging_section)
        if log_error is not None:
            return log_error

    workers = data["server"]["workers"]
    if workers > 16 and "pool_size" not in data["database"]:
        return "missing_pool_size_for_high_workers"

    return "valid_config"
