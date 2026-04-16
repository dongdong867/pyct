"""Base64 payload classification benchmark target.

Category: Encoding detection with content-type inference
Intent: Decode a base64-encoded payload and classify its content type (JSON, XML,
    CSV, plain text, binary) with structural validation after detection.
Challenge: The base64 decode step creates a non-trivial input transformation that
    the solver must invert, then the decoded content branches into format detectors
    each with sub-validation, layering constraints on top of the encoding barrier.
"""

from __future__ import annotations

import base64
import json

MAX_DECODED_LENGTH = 10000


def _classify_json(decoded: str) -> str:
    """Attempt to validate decoded text as JSON and sub-classify."""
    try:
        data = json.loads(decoded)
    except (json.JSONDecodeError, ValueError):
        return "invalid_json"
    if isinstance(data, dict):
        return "valid_json_object"
    if isinstance(data, list):
        return "valid_json_array"
    return "valid_json_primitive"


def _classify_xml(decoded: str) -> str:
    """Basic XML structure classification by tag presence."""
    if "</" not in decoded and "/>" not in decoded:
        return "xml_unclosed"
    if decoded.lstrip().startswith("<?xml"):
        return "xml_with_declaration"
    return "xml_document"


def _classify_csv(decoded: str) -> str:
    """Basic CSV structure classification by row/column consistency."""
    lines = decoded.strip().split("\n")
    if len(lines) < 2:
        return "csv_single_row"
    header_cols = len(lines[0].split(","))
    data_cols = len(lines[1].split(","))
    if header_cols != data_cols:
        return "csv_ragged"
    return "csv_data"


def _is_binary(decoded_bytes: bytes) -> bool:
    """Check if byte content is likely binary (high ratio of non-printable chars)."""
    printable = set(range(32, 127)) | {9, 10, 13}
    non_printable = sum(1 for b in decoded_bytes if b not in printable)
    return non_printable > len(decoded_bytes) * 0.1


def _classify_text(decoded: str) -> str:
    """Classify decoded text that matched no structured format."""
    stripped = decoded.strip()
    if all(ch.isprintable() or ch in "\n\r\t" for ch in stripped):
        return "plain_text"
    return "binary_data"


def base64_payload_classification(payload: str) -> str:
    """Decode a base64 payload and classify its content type."""
    if len(payload) == 0:
        return "invalid_empty"

    try:
        decoded_bytes = base64.b64decode(payload, validate=True)
    except Exception:
        return "invalid_base64"

    if len(decoded_bytes) == 0:
        return "empty_payload"
    if len(decoded_bytes) > MAX_DECODED_LENGTH:
        return "too_large"

    if _is_binary(decoded_bytes):
        return "binary_data"

    decoded = decoded_bytes.decode("utf-8", errors="replace")
    trimmed = decoded.lstrip()

    if trimmed.startswith("{") or trimmed.startswith("["):
        return _classify_json(decoded)
    if trimmed.startswith("<"):
        return _classify_xml(decoded)
    if "," in decoded and "\n" in decoded:
        return _classify_csv(decoded)

    return _classify_text(decoded)
