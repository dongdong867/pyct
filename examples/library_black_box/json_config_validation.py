"""JSON configuration validation benchmark target.

Category: Structured data parsing with nested validation
Intent: Parse a JSON config string and validate required keys, value constraints,
    optional nested settings, and API key format.
Challenge: Combines JSON parsing failure paths with multi-key presence checks,
    enum validation, version format constraints, nested-object traversal, and
    string length checks — each adding independent branching dimensions.
"""

from __future__ import annotations

import json

VALID_MODES = frozenset({"production", "staging", "development"})

MIN_API_KEY_LENGTH = 16


def _validate_mode(config: dict) -> str | None:
    """Validate the required 'mode' key. Returns error classification or None."""
    if "mode" not in config:
        return "missing_mode"
    mode = config["mode"]
    if not isinstance(mode, str):
        return "invalid_mode_type"
    if mode not in VALID_MODES:
        return "invalid_mode_value"
    return None


def _validate_version(config: dict) -> str | None:
    """Validate the 'version' key format. Returns error classification or None."""
    version = config.get("version")
    if version is None:
        return None
    if not isinstance(version, str):
        return "invalid_version_type"
    if "." not in version:
        return "invalid_version_no_dot"
    parts = version.split(".")
    for part in parts:
        if not part.isdigit():
            return "invalid_version_not_numeric"
    return None


def _validate_settings(config: dict) -> str | None:
    """Validate the optional 'settings' sub-object. Returns error or None."""
    settings = config.get("settings")
    if settings is None:
        return None
    if not isinstance(settings, dict):
        return "invalid_settings_type"
    timeout = settings.get("timeout")
    if timeout is not None:
        if not isinstance(timeout, (int, float)):
            return "invalid_timeout_type"
        if timeout <= 0:
            return "invalid_timeout_value"
    retries = settings.get("retries")
    if retries is not None:
        if not isinstance(retries, int):
            return "invalid_retries_type"
        if retries < 0 or retries > 10:
            return "invalid_retries_range"
    return None


def _validate_api_key(config: dict) -> str | None:
    """Validate the optional API key field. Returns error or None."""
    api_key = config.get("api_key")
    if api_key is None:
        return None
    if not isinstance(api_key, str):
        return "invalid_api_key_type"
    if len(api_key) < MIN_API_KEY_LENGTH:
        return "api_key_too_short"
    return None


def json_config_validation(config_str: str) -> str:
    """Parse and validate a JSON configuration string."""
    if len(config_str) == 0:
        return "invalid_empty"
    if not config_str.lstrip().startswith("{"):
        return "invalid_not_object_start"

    try:
        config = json.loads(config_str)
    except (json.JSONDecodeError, ValueError):
        return "invalid_json"

    if not isinstance(config, dict):
        return "invalid_not_object"

    mode_err = _validate_mode(config)
    if mode_err is not None:
        return mode_err

    version_err = _validate_version(config)
    if version_err is not None:
        return version_err

    settings_err = _validate_settings(config)
    if settings_err is not None:
        return settings_err

    key_err = _validate_api_key(config)
    if key_err is not None:
        return key_err

    return f"valid_{config['mode']}"
