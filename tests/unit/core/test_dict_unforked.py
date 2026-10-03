"""A tracked dict changed in a way pyct answers without a fork, as under a tracked key: such a
change may touch any key on another input, so no lookup after it is decided, and the fewest keys
count only what holds whichever key it touched."""

from collections.abc import Callable
from typing import Any

import pytest

from pyct.core.dicts import ConcolicDict
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_dicts import decided, forks, tracked

# each change under a tracked key, which pyct answers without a fork; `name` is "pyct1", which
# the argument does not hold, so on another input the change may touch "a" or "b". Each with the
# fewest keys the dict holds after it: the two it knew before, one less after a removal
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
    name = ConcolicStr.made("pyct1", "name", sink)
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


def test_a_dict_changed_without_a_fork_decides_nothing_its_copies_decide() -> None:
    config, sink = tracked({"a": 1})
    name = ConcolicStr.made("pyct1", "name", sink)
    kept = config.copy()
    assert "a" in config

    config[name] = 0
    assert "a" in config and "a" in kept

    # the copy made before the change still knows the key it found
    assert decided(sink) == [(["in", "'a'", "config"], True)]


def test_a_store_that_hit_a_key_the_argument_holds_decides_no_count_its_term_misses() -> None:
    # `d |= {n: 1}` with n "a" on {"a": 1} grows nothing here, so the size term stays `len(d)`,
    # which the empty argument with the same n makes 0, though the dict then holds n
    config, sink = tracked({"a": 1})
    name = ConcolicStr.made("a", "name", sink)

    config |= {name: 1}
    assert bool(config)

    assert forks(sink) == [(["!=", ["len", "config"], 0], True)]
    assert decided(sink) == []


def test_a_removal_answered_without_a_fork_after_a_mark_may_take_a_key() -> None:
    config, sink = tracked({})
    config["b"] = 1
    del config["b"]
    name = ConcolicStr.made("pyct1", "name", sink)
    config[name] = 0

    # "b" is answered from what the target changed, with no fork; n "b" would have stored it
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
