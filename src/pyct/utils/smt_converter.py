from __future__ import annotations

from pyct.utils.constants import SMTConstants


def py2smt(obj: bool | int | float | str) -> str:
    """
    Convert Python object to SMT-LIB2 string representation.

    Args:
        obj: Python object to convert

    Returns:
        SMT-LIB2 format string

    Raises:
        NotImplementedError: If type is not supported

    Examples:
        >>> py2smt(True)
        'true'
        >>> py2smt(-42)
        '(- 42)'
        >>> py2smt("hello")
        '"hello"'
    """
    converters = {
        bool: _convert_bool,
        int: _convert_number,
        float: _convert_number,
        str: _convert_string,
    }

    converter = converters.get(type(obj))
    if converter is None:
        raise NotImplementedError(f"SMT conversion not supported for type {type(obj)}")

    return converter(obj)


def _convert_bool(value: bool) -> str:
    """Convert boolean to SMT format."""
    return SMTConstants.TRUE if value else SMTConstants.FALSE


def _convert_number(value: int | float) -> str:
    """Convert number to SMT format."""
    if value < 0:
        return f"{SMTConstants.NEGATIVE_PREFIX}{-value}{SMTConstants.NEGATIVE_SUFFIX}"
    return str(value)


def _convert_string(value: str) -> str:
    """Convert string to SMT format with proper escaping."""
    escaped = _apply_escape_mappings(value)
    unicode_escaped = _escape_unicode(escaped)
    return f'"{unicode_escaped}"'


def _apply_escape_mappings(value: str) -> str:
    """Apply escape mappings to string."""
    result = value
    for char, replacement in SMTConstants.ESCAPE_MAPPINGS.items():
        result = result.replace(char, replacement)
    return result


def _escape_unicode(value: str) -> str:
    """Escape unicode characters to SMT format."""
    result = []
    for char in value:
        if ord(char) > 127:
            hex_value = hex(ord(char))[2:]
            result.append(f"{SMTConstants.UNICODE_PREFIX}{hex_value}{SMTConstants.UNICODE_SUFFIX}")
        else:
            result.append(char)
    return "".join(result)
