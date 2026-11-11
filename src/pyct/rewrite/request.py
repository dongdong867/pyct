"""The request a rewrites ask sends, built from the source: the condition and the earlier
conditions of its path as Python writes them, and the input's values as JSON."""

from __future__ import annotations

import ast
import functools
import json
from dataclasses import dataclass

from pyct.core.foundation.branch import Site
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.provider import EarlierTry, RewriteRequest, Side

# the earlier conditions a request holds at most, the nearest the condition
EARLIER = 30
# the characters of JSON each parameter's value may take
VALUE_SIZE = 2_000


@dataclass(frozen=True)
class About:
    """Where the condition sits: its place as the recording keys it, its site as stderr writes
    it, and the source of the function that holds it."""

    place: str
    site: str
    code: str


def request_for(given: GivenUp, about: About, tries: tuple[EarlierTry, ...]) -> RewriteRequest:
    """The request for a condition the solver gave up on, with this moment's earlier tries."""
    plan = given.plan
    earlier = [fork for fork in plan.prefix[:-1] if not fork.raising]
    sides = list(dict.fromkeys((fork.site, fork.taken) for fork in earlier))[-EARLIER:]
    return RewriteRequest(
        place=about.place,
        site=about.site,
        condition=Side(condition_text(given.condition.site), given.condition.side),
        earlier=tuple(Side(condition_text(site), side) for site, side in sides),
        code=about.code,
        args=tuple((name, _value(value)) for name, value in given.origin.args.items()),
        answer=given.answer.value,
        tries=tries,
    )


def condition_text(site: Site) -> str:
    """The condition at ``site`` as Python writes it: the outermost expression that starts
    there, an ``and`` or ``or`` aside, since each of its operands forks at its own start. The
    site written out when its file does not read or holds no expression there."""
    found = _starting(site.file).get((site.line, site.col))
    return f"the condition at {site.file}:{site.line}:{site.col}" if found is None else found


@functools.lru_cache(maxsize=16)
def _starting(file: str) -> dict[tuple[int, int], str]:
    """Each position an expression of the file starts at, with the outermost such expression's
    text. Read once per file."""
    try:
        with open(file, encoding="utf-8") as opened:
            source = opened.read()
        tree = ast.parse(source, filename=file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return {}
    texts: dict[tuple[int, int], str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.expr) or isinstance(node, ast.BoolOp):
            continue
        key = (node.lineno, node.col_offset)
        text = ast.get_source_segment(source, node)
        if text is not None and len(text) > len(texts.get(key, "")):
            texts[key] = text
    return texts


def _value(value: object) -> str:
    """The value as JSON, or as Python writes it when JSON cannot, cut to ``VALUE_SIZE``."""
    try:
        text = json.dumps(value)
    except (TypeError, ValueError, RecursionError):
        text = repr(value)
    return text[:VALUE_SIZE]
