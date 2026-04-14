"""
Parse solver output to extract models.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("ct.solver.parser")


class ModelParser:
    """Parses SMT solver output to extract variable assignments."""

    VAR_SUFFIX = "_VAR"

    def parse_model(self, output_lines: list[str], var_to_types: dict[str, str]) -> dict[str, Any]:
        """
        Parse solver output to extract model.

        Args:
            output_lines: Lines of solver output (excluding status line)
            var_to_types: Mapping of variable names to types

        Returns:
            Dictionary mapping variable names to values

        Examples:
            >>> parser = ModelParser()
            >>> lines = ["((x_VAR 42))", "((y_VAR true))"]
            >>> types = {"x_VAR": "Int", "y_VAR": "Bool"}
            >>> parser.parse_model(lines, types)
            {"x": 42, "y": True}
        """
        model = {}

        for line in output_lines:
            if not line.strip():
                continue

            name, value = self._parse_assignment(line)
            var_type = var_to_types.get(name)

            if var_type is None:
                log.warning("Unknown variable %s in model", name)
                continue

            parsed_value = self._parse_value(value, var_type)
            clean_name = self._remove_var_suffix(name)
            model[clean_name] = parsed_value

        return model

    def _parse_assignment(self, line: str) -> tuple[str, str]:
        """
        Parse a single assignment line.

        Args:
            line: Line like "((name value))"

        Returns:
            Tuple of (name, value)
        """
        if not (line.startswith("((") and line.endswith("))")):
            raise ValueError(f"Invalid assignment format: {line}")

        content = line[2:-2]  # Remove "((" and "))"
        name, value = content.split(" ", 1)
        return name, value

    def _parse_value(self, value: str, var_type: str) -> Any:
        """
        Parse value based on its type.

        Args:
            value: String representation of value
            var_type: SMT type ("Bool", "Int", "Real", "String")

        Returns:
            Parsed Python value
        """
        parsers = {
            "Bool": self._parse_bool,
            "Int": self._parse_int,
            "Real": self._parse_real,
            "String": self._parse_string,
        }

        parser = parsers.get(var_type)
        if parser is None:
            raise NotImplementedError(f"Unsupported type: {var_type}")

        return parser(value)

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse boolean value."""
        if value == "true":
            return True
        elif value == "false":
            return False
        else:
            raise ValueError(f"Invalid boolean value: {value}")

    @staticmethod
    def _parse_int(value: str) -> int:
        """Parse integer value, handling negatives like "(- 42)"."""
        if value.startswith("("):
            # Negative number: "(- 42)"
            parts = value.replace("(", "").replace(")", "").split()
            return -int(parts[1])
        else:
            return int(value)

    @staticmethod
    def _parse_real(value: str) -> float:
        """Parse real/float value, handling negatives."""
        if value.startswith("("):
            # Negative number: "(- 3.14)"
            parts = value.replace("(", "").replace(")", "").split()
            return -float(parts[1])
        else:
            return float(value)

    @staticmethod
    def _parse_string(value: str) -> str:
        """Parse string value, handling escapes."""
        if not (value.startswith('"') and value.endswith('"')):
            raise ValueError(f"Invalid string value: {value}")

        # Remove quotes
        content = value[1:-1]

        # Unescape in reverse order of encoding
        unescaped = (
            content.replace('""', '"')
            .replace("\\t", "\t")
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\\\", "\\")
        )

        return unescaped

    def _remove_var_suffix(self, name: str) -> str:
        """Remove _VAR suffix from variable name."""
        if name.endswith(self.VAR_SUFFIX):
            return name[: -len(self.VAR_SUFFIX)]
        return name
