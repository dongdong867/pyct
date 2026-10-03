"""A tracked dict changed in a way pyct answers without a fork, as under a tracked key of
another kind than the dict's keys: such a change may touch any key on another input, so no
lookup after it is decided, and the fewest keys count only what holds whichever key it touched.
A change under a tracked key of the dict's own kind is followed by its forks, and marks
nothing."""

from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.branch import SinkItem
from pyct.core.dicts import ConcolicDict
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import decided, forks, tracked

# each change under a tracked int into a dict whose keys are strs, which pyct answers without a
# fork and so marks, whatever the key may equal. Each with the fewest keys the dict holds after
# it: the two it knew before, one less after a removal
UNFORKED_CHANGES: dict[str, tuple[Callable[[Any, Any], object], int]] = {
    "store": (lambda c, name: c.__setitem__(name, 0), 2),
    "pop": (lambda c, name: c.pop(name, None), 1),
    "setdefault": (lambda c, name: c.setdefault(name, 0), 2),
    "update": (lambda c, name: c.update({name: 0}), 2),
    "in place or": (lambda c, name: c.__ior__({name: 0}), 2),
    "or": (lambda c, name: c | {name: 0}, 2),
    "reflected or": (lambda c, name: {name: 0} | c, 2),
}


@pytest.mark.parametrize("change", list(UNFORKED_CHANGES))
def test_after_a_forkless_change_lookups_are_forks_and_counts_reach_only_the_floor(
    change: str,
) -> None:
    config, sink = tracked({"a": 1})
    config["b"] = 2  # changed, so a tracked key's lookup is Python's own
    name = ConcolicInt.made(7, "name", sink)
    assert "a" in config
    made, fewest = UNFORKED_CHANGES[change]

    changed = made(config, name)
    after = changed if isinstance(changed, ConcolicDict) else config
    asked, known = len(forks(sink)), len(decided(sink))
    assert "a" in after and bool(after)
    for _ in after:
        pass

    # the lookup is a fork; the truth test and the passes the fewest keys reach are facts
    heads = [str(part[0]) for part, _ in forks(sink)[asked:] if isinstance(part, list)]
    assert [head for head in heads if head != "=="] == ["in", *[">"] * (len(after) + 1 - fewest)]
    facts = [str(part[0]) for part, _ in decided(sink)[known:] if isinstance(part, list)]
    assert facts == ["!=", *[">"] * fewest]


# each change above under a tracked str, which a str-keyed dict follows, but `{n: 0} | c`, which
# keeps v2's own answer since the solver may move n among the other dict's keys
FOLLOWED_CHANGES = [change for change in UNFORKED_CHANGES if change != "reflected or"]


@pytest.mark.parametrize("change", FOLLOWED_CHANGES)
def test_a_followed_tracked_change_marks_nothing_and_its_forks_decide_what_follows(
    change: str,
) -> None:
    config, sink = tracked({"aa": 1})
    config["bb"] = 2
    name = ConcolicStr.made("pyct1", "name", sink)
    assert "aa" in config
    made, _ = UNFORKED_CHANGES[change]

    changed = made(config, name)
    after = changed if isinstance(changed, ConcolicDict) else config
    asked = len(forks(sink))
    assert "aa" in after and bool(after)

    # the change asked whether name is "bb" and whether the argument holds it, so "aa" is decided
    # once name is not "aa", which a store asks; the pop found nothing, so it changed nothing
    stored = [] if change == "pop" else [(["==", "name", "'aa'"], False)]
    assert not after.unforked
    assert forks(sink)[asked:] == stored
    assert decided(sink)[-2:] == [
        (["in", "'aa'", "config"], True),
        (["!=", after.size_term(), 0], True),
    ]


def test_a_copy_made_before_a_forkless_change_still_decides_its_repeat_lookup() -> None:
    config, sink = tracked({"a": 1})
    kept = config.copy()
    assert "a" in config

    config[ConcolicInt.made(7, "n", sink)] = 0
    assert "a" in config and "a" in kept

    # the copy made before the change still knows the key it found
    assert decided(sink) == [(["in", "'a'", "config"], True)]


def test_a_store_that_hit_a_key_the_argument_holds_decides_no_count_its_term_misses() -> None:
    # `d |= {n: 1}` with n 1 on {1: 1} grows nothing here, so the size term stays `len(d)`,
    # which the empty argument with the same n makes 0, though the dict then holds n
    sink: list[SinkItem] = []
    config = ConcolicDict.made({1: 1}, "config", sink)
    name = ConcolicInt.made(1, "name", sink)

    config |= {name: 1}
    assert bool(config)

    assert forks(sink) == [(["!=", ["len", "config"], 0], True)]
    assert decided(sink) == []


def test_a_removal_answered_without_a_fork_after_a_mark_may_take_a_key() -> None:
    config, sink = tracked({})
    config["b"] = 1
    del config["b"]
    config[ConcolicInt.made(7, "name", sink)] = 0

    # "b" is answered from what the target changed, with no fork; a forkless store may have
    # stored it
    assert config.pop("b", None) is None
    assert bool(config)

    assert forks(sink)[-1] == (["!=", ["+", ["len", "config"], 1], 0], True)
    assert decided(sink) == []


def test_a_merge_with_the_dict_on_the_right_marks_only_what_it_makes() -> None:
    config, sink = tracked({"a": 1})
    name = ConcolicStr.made("pyct1", "name", sink)
    assert "a" in config

    made = {name: 0} | config
    assert "a" in config and "a" in made

    # the dict itself did not change, so its lookup holds what the first found
    assert decided(sink) == [(["in", "'a'", "config"], True)]


# each removal over a key of each kind, which Python answers on a marked dict; the key is not
# there on this input, but a forkless store may have put it there on another
REMOVALS: dict[str, Callable[[Any], object]] = {
    "pop a tuple": lambda c: c.pop(("b",), None),
    "pop a float": lambda c: c.pop(1.5, None),
    "pop a str": lambda c: c.pop("b", None),
    "pop a tracked key": lambda c: c.pop(ConcolicStr.made("b", "m", []), None),
}


@pytest.mark.parametrize("removal", list(REMOVALS))
def test_every_removal_on_a_marked_dict_may_take_a_key(removal: str) -> None:
    config, sink = tracked({})
    name = ConcolicStr.made("pyct1", "name", sink)
    config[(name,)] = 1

    REMOVALS[removal](config)
    assert bool(config)

    assert decided(sink) == []


def test_a_removal_that_raises_here_may_take_a_key_on_another_input() -> None:
    config, sink = tracked({})
    flag = ConcolicStr.made("b", "m", sink) == "a"
    config |= {flag: 1}
    other = ConcolicStr.made("a", "n", sink) == "a"

    # the key is not there on this input, so `del` raises; with m "a" it removes the only key
    with pytest.raises(KeyError):
        del config[other]
    assert bool(config)

    assert decided(sink) == []
