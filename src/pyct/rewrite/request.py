"""The request a rewrites ask sends, built from the source: the condition and the earlier
conditions of its path as Python writes them, and the input's values as JSON, or as Python writes
them when JSON cannot hold them, each value that is or holds an object (``pyct.rewrite.kinds``) as a
placeholder written without running the target's code: an object the input builds as its class and
the arguments it is built from. It names a file by its module, never by its path."""

from __future__ import annotations

import ast
import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pyct.binding.annotations import Builds
from pyct.binding.builds import object_form
from pyct.binding.classes import name_of
from pyct.binding.seed_keys import CLASS_KEY
from pyct.binding.stored import plain_data
from pyct.core.foundation.branch import Site
from pyct.rewrite.ask import GivenUp
from pyct.rewrite.kinds import Kind, Kinds
from pyct.rewrite.provider import EarlierTry, RewriteRequest, Side

# the earlier conditions a request holds at most, the nearest the condition
EARLIER = 30
# the characters each parameter's value may take, in a request and in a try's reason alike
VALUE_SIZE = 2_000
# a value that holds an object inside a list, tuple or dict, or an object the input builds from a
# dict or list whose class the request cannot name
HOLDS_OBJECT = "<holds an object>"


@dataclass(frozen=True)
class About:
    """Where the condition sits: its place, ``module:line:col``, the source of the function
    that holds it, and each file of the path with its module as the run names it."""

    place: str
    code: str
    modules: Mapping[str, str]


def request_for(
    given: GivenUp,
    about: About,
    tries: tuple[EarlierTry, ...],
    holders: tuple[str, ...],
    kinds: Kinds,
) -> RewriteRequest:
    """The request for a condition the solver gave up on, with this moment's earlier tries and
    the parameters a rewrite may not read, since each holds an object inside a list, tuple or
    dict. ``kinds`` tells the input's objects apart, the method's ``self`` among them."""
    plan = given.plan
    earlier = [fork for fork in plan.prefix[:-1] if not fork.raising]
    # each condition at its last place on the path, so the nearest ones stay
    last = {(fork.site, fork.taken): at for at, fork in enumerate(earlier)}
    sides = sorted(last, key=last.__getitem__)[-EARLIER:]
    return RewriteRequest(
        place=about.place,
        condition=Side(_text(given.condition.site, about), given.condition.side),
        earlier=tuple(Side(_text(site, about), side) for site, side in sides),
        code=about.code,
        args=args_text(given.origin.args, kinds),
        answer=given.answer.value,
        tries=tries,
        holders=holders,
    )


def condition_text(site: Site, module: str) -> str:
    """The condition at ``site`` as Python writes it: the outermost expression that starts
    there, an ``and`` or ``or`` aside, since each of its operands forks at its own start. The
    site written out by ``module``'s name when its file does not read or holds no expression
    there."""
    found = _starting(site.file).get((site.line, site.col))
    return f"the condition at {module}:{site.line}:{site.col}" if found is None else found


def _text(site: Site, about: About) -> str:
    """The condition at ``site``, its module named as ``about`` names it."""
    return condition_text(site, about.modules[site.file])


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


def args_text(args: Mapping[str, object], kinds: Kinds) -> tuple[tuple[str, str], ...]:
    """Each argument's name, with its value as ``value_text`` writes it, or an object the input
    builds as ``built_text`` writes it."""
    return tuple((name, _arg_text(name, value, kinds)) for name, value in args.items())


def _arg_text(name: str, value: object, kinds: Kinds) -> str:
    kind = kinds.of(name, value)
    if kind is Kind.OBJECT and (type(value) is dict or type(value) is list):
        return built_text(value, _built_class(name, value, kinds))
    return value_text(value, kind)


def _built_class(name: str, value: object, kinds: Kinds) -> str | None:
    """The name of the class the input builds ``value`` under ``name`` as: the one its object
    form names, without its module, the one its hint names, or the method's own class for its
    ``self``. None when the request cannot name one."""
    if object_form(value):
        named = value[CLASS_KEY]
        return named.rpartition("::")[2] if type(named) is str else None
    check = kinds.checks.get(name)
    if isinstance(check, Builds):
        return name_of(check.cls)
    if name == kinds.self_name and kinds.self_class is not None:
        return name_of(kinds.self_class)
    return None


def built_text(value: dict[str, object] | list[object], cls: str | None) -> str:
    """An object the input builds from ``value`` as ``<Name object, built from ARGS>``, ``ARGS``
    its arguments as JSON with no ``"__class__"``; as ``<Name object>`` when they are no plain
    data, JSON cannot hold them or the text runs past ``VALUE_SIZE``, and as ``HOLDS_OBJECT``
    when ``cls`` names no class."""
    if cls is None:
        return HOLDS_OBJECT
    bare = f"<{cls} object>"
    if not plain_data(value):
        return bare
    shown = (
        {key: each for key, each in value.items() if key != CLASS_KEY}
        if type(value) is dict
        else value
    )
    try:
        written = f"<{cls} object, built from {json.dumps(shown)}>"
    except (TypeError, ValueError, RecursionError):
        return bare
    return written if len(written) <= VALUE_SIZE else bare


def value_text(value: object, kind: Kind) -> str:
    """A parameter's value as JSON, or as Python writes it when JSON cannot, cut to
    ``VALUE_SIZE`` characters. A value of another ``kind`` than plain is never handed to
    ``json`` or ``repr``, which can run the target's code: an instance of ``Name`` is
    ``<Name object>``, its name read through ``type``'s own descriptor, and any other such
    value ``HOLDS_OBJECT``."""
    if kind is not Kind.PLAIN:
        held = type(value)
        if kind is Kind.HOLDS_OBJECT or held is dict or held is list:
            return HOLDS_OBJECT
        return f"<{name_of(held)} object>"
    try:
        return json.dumps(value)[:VALUE_SIZE]
    except (TypeError, ValueError, RecursionError):
        return repr(value)[:VALUE_SIZE]
