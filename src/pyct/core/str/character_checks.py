from __future__ import annotations

import logging
from typing import Any

from pyct.utils import concolic_converter
from pyct.utils.smt_converter import py2smt

log = logging.getLogger("ct.con.str.checks")


class CharacterChecks:
    """Character classification methods with symbolic tracking."""

    @staticmethod
    def isalpha(concolic_str: Any) -> Any:
        """Check if string is alphabetic."""
        concrete = str.isalpha(concolic_str)
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            [
                "re.+",
                [
                    "re.union",
                    ["re.range", py2smt("A"), py2smt("Z")],
                    ["re.range", py2smt("a"), py2smt("z")],
                ],
            ],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def isalnum(concolic_str: Any) -> Any:
        """Check if string is alphanumeric."""
        concrete = str.isalnum(concolic_str)
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            [
                "re.+",
                [
                    "re.union",
                    [
                        "re.union",
                        ["re.range", py2smt("A"), py2smt("Z")],
                        ["re.range", py2smt("a"), py2smt("z")],
                    ],
                    ["re.range", py2smt("0"), py2smt("9")],
                ],
            ],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def isdigit(concolic_str: Any) -> Any:
        """Check if string is all digits."""
        concrete = str.isdigit(concolic_str)
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            ["re.+", ["re.range", py2smt("0"), py2smt("9")]],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def isnumeric(concolic_str: Any) -> Any:
        """Check if string is numeric."""
        concrete = str.isnumeric(concolic_str)

        # Approximation: same as isdigit for SMT
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            ["re.+", ["re.range", py2smt("0"), py2smt("9")]],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def islower(concolic_str: Any) -> Any:
        """Check if string is lowercase."""
        concrete = str.islower(concolic_str)
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            ["re.+", ["re.range", py2smt("a"), py2smt("z")]],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def isupper(concolic_str: Any) -> Any:
        """Check if string is uppercase."""
        concrete = str.isupper(concolic_str)
        symbolic_expr = [
            "str.in_re",
            concolic_str,
            ["re.+", ["re.range", py2smt("A"), py2smt("Z")]],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )

    @staticmethod
    def is_integer_string(concolic_str: Any) -> Any:
        """Check if string represents an integer (helper for conversion)."""
        import re

        concrete = re.compile(r"^[-]?\d+$").match(str(concolic_str)) is not None
        symbolic_expr = [
            "str.in_re",
            [
                "ite",
                ["str.prefixof", py2smt("-"), concolic_str],
                ["str.substr", concolic_str, "1", ["str.len", concolic_str]],
                concolic_str,
            ],
            ["re.+", ["re.range", py2smt("0"), py2smt("9")]],
        ]

        return concolic_converter.wrap_concolic(
            concrete, symbolic_expr, concolic_str.engine
        )
