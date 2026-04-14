from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

from pyct.core.str.helpers import (
    SubstringHelper,
    ensure_concolic_int,
    ensure_concolic_str,
)
from pyct.utils import concolic_converter
from pyct.utils.smt_converter import py2smt

log = logging.getLogger("ct.con.str.queries")


@dataclass(frozen=True)
class _SearchArgs:
    """Prepared arguments for string search operations."""

    sub: Any
    start: Any
    search_region: Any


def _prepare_search_args(concolic_str: Any, args: tuple) -> _SearchArgs:
    """Prepare search arguments shared by find/index/count/startswith/endswith."""
    args_list = list(copy.copy(args))
    engine = concolic_str.engine

    sub = ensure_concolic_str(args_list[0], engine)
    start = ensure_concolic_int(
        args_list[1] if len(args_list) > 1 else 0,
        engine,
    )
    end = ensure_concolic_int(
        args_list[2]
        if len(args_list) > 2
        else len(concolic_converter.unwrap_concolic(concolic_str)),
        engine,
    )
    search_region = SubstringHelper.substr(concolic_str, start, end)

    return _SearchArgs(sub=sub, start=start, search_region=search_region)


class StringQueries:
    """String searching and querying operations."""

    @staticmethod
    def find(concolic_str: Any, *args) -> Any:
        """Find substring, return index or -1."""
        concrete = str.find(
            concolic_str,
            *map(concolic_converter.unwrap_concolic, args),
        )
        sa = _prepare_search_args(concolic_str, args)

        (sa.sub in sa.search_region).__bool__()

        symbolic_expr = ["+", sa.start, ["str.indexof", sa.search_region, sa.sub, "0"]]
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            concolic_str.engine,
        )

    @staticmethod
    def index(concolic_str: Any, *args) -> Any:
        """Find substring, return index or raise ValueError."""
        concrete = str.index(
            concolic_str,
            *map(concolic_converter.unwrap_concolic, args),
        )
        sa = _prepare_search_args(concolic_str, args)

        symbolic_expr = ["str.indexof", sa.search_region, sa.sub, "0"]
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            concolic_str.engine,
        )

    @staticmethod
    def count(concolic_str: Any, *args) -> Any:
        """Count non-overlapping occurrences of substring."""
        concrete = str.count(
            concolic_str,
            *map(concolic_converter.unwrap_concolic, args),
        )
        sa = _prepare_search_args(concolic_str, args)

        (sa.sub in sa.search_region).__bool__()

        symbolic_expr = _build_count_expression(sa.search_region, sa.sub)
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            concolic_str.engine,
        )

    @staticmethod
    def startswith(concolic_str: Any, *args) -> Any:
        """Check if string starts with prefix."""
        concrete = str.startswith(
            concolic_str,
            *map(concolic_converter.unwrap_concolic, args),
        )
        sa = _prepare_search_args(concolic_str, args)

        symbolic_expr = ["str.prefixof", sa.sub, sa.search_region]
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            concolic_str.engine,
        )

    @staticmethod
    def endswith(concolic_str: Any, *args) -> Any:
        """Check if string ends with suffix."""
        concrete = str.endswith(
            concolic_str,
            *map(concolic_converter.unwrap_concolic, args),
        )
        sa = _prepare_search_args(concolic_str, args)

        symbolic_expr = ["str.suffixof", sa.sub, sa.search_region]
        return concolic_converter.wrap_concolic(
            concrete,
            symbolic_expr,
            concolic_str.engine,
        )


def _build_count_expression(search_region: Any, sub: Any) -> list:
    """Build SMT expression for counting substring occurrences.

    count = (len(main) - len(replace_all(main, sub, ""))) / len(sub)
    Special case: if sub is empty, return len(main) + 1.
    """
    return [
        "ite",
        ["<=", ["str.len", sub], "0"],
        ["+", "1", ["str.len", search_region]],
        [
            "div",
            [
                "-",
                ["str.len", search_region],
                ["str.len", ["str.replace_all", search_region, sub, py2smt("")]],
            ],
            ["str.len", sub],
        ],
    ]
