"""Turn a seed dict into the arguments the target is called with."""

import json
from collections.abc import Callable, Mapping
from typing import TypeGuard

from pyct.core.branch import BranchSink, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# what a walk makes of one value bind tracks, given the access that reaches it
type AtLeaf = Callable[[int | str, Expression], object]


def bind(seed: Mapping[str, object], sink: BranchSink) -> dict[str, object]:
    """Give every int and str in the seed, at any depth, its access and the sink.

    A parameter's own value is named by the parameter. A value inside a dict
    or a list is named by the access that reaches it, one ``["[]", <container>,
    <key>]`` per step, so ``config["server"]["port"]`` is
    ``["[]", ["[]", "config", "'server'"], "'port'"]``. Every dict and list is
    rebuilt, so the target gets a copy of its own: a change it makes reaches
    neither the seed nor a later input. A bool is an int to Python but not a
    number to bind: it has no ``<`` worth tracking. Every other value passes
    through as it came.
    """
    return walked(seed, lambda value, access: _tracked(value, access, sink))


def leaves(seed: Mapping[str, object]) -> dict[str, type]:
    """The name and type of every value ``bind`` tracks, in the seed's order.

    This is what the solver is allowed to answer about: nothing else in the
    seed carries a condition back. Each is named as ``leaf_name`` names it.
    """
    found: dict[str, type] = {}

    def note(value: int | str, access: Expression) -> object:
        found[leaf_name(access)] = type(value)
        return value

    walked(seed, note)
    return found


def leaf_name(access: Expression) -> str:
    """The name a tracked value goes by in a model: its parameter's, or its access as JSON.

    A parameter's name is an identifier and an access's JSON opens with a
    bracket, so no two tracked values share a name.
    """
    return access if isinstance(access, str) else json.dumps(access)


def walked(seed: Mapping[str, object], at_leaf: AtLeaf) -> dict[str, object]:
    """The seed rebuilt, with ``at_leaf``'s answer in place of every value bind tracks.

    bind, leaves and the model all read this one walk, so they cannot
    disagree about which values are tracked or what each is named.
    """
    return {name: _rebuilt(value, name, at_leaf) for name, value in seed.items()}


def _binds(value: object) -> TypeGuard[int | str]:
    """Whether bind tracks this value: the one rule the walk reads."""
    return isinstance(value, int | str) and not isinstance(value, bool)


def _rebuilt(value: object, access: Expression, at_leaf: AtLeaf) -> object:
    """One value of the seed, with every tracked value under it handed to ``at_leaf``.

    A dict and a list, and not their subclasses, are walked and rebuilt as
    the same type; a dict's value is walked when its key can be written as a
    literal (see ``_key``).
    """
    if _binds(value):
        return at_leaf(value, access)
    if isinstance(value, list) and type(value) is list:
        return [_rebuilt(item, ["[]", access, index], at_leaf) for index, item in enumerate(value)]
    if isinstance(value, dict) and type(value) is dict:
        return {key: _item(key, item, access, at_leaf) for key, item in value.items()}
    return value


def _item(key: object, item: object, container: Expression, at_leaf: AtLeaf) -> object:
    """A dict's value, walked when its key is one an access can name."""
    literal = _key(key)
    return item if literal is None else _rebuilt(item, ["[]", container, literal], at_leaf)


def _key(key: object) -> Expression | None:
    """A key as an access writes it: a str in its Python quotes, an int as itself.

    Any other key is None, and the value under it passes through as it came.
    """
    if isinstance(key, str):
        # str's own repr: a key of the target's own str subclass may print itself another way
        return str.__repr__(key)
    if isinstance(key, int) and not isinstance(key, bool):
        return int(key)
    return None


def _tracked(value: int | str, access: Expression, sink: BranchSink) -> object:
    if isinstance(value, str):
        return ConcolicStr(value, expression=access, sink=sink)
    return ConcolicInt(value, expression=access, sink=sink)
