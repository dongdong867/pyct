"""A module's live builtins: every dict method answers and writes as on `builtins`' own dict."""

import builtins
import copy
import pickle
from collections.abc import Iterator

import pytest

from pyct.core import bound
from pyct.intercept.wrap import LiveBuiltins

PROBE = "_pyct_live_probe"


@pytest.fixture
def live() -> Iterator[LiveBuiltins]:
    """A module's builtins, and no probe name left in `builtins` when the test ends."""
    yield LiveBuiltins()
    vars(builtins).pop(PROBE, None)


def expected() -> dict[str, object]:
    """What a module of the target's package reads: `builtins` now, with pyct's three."""
    return {
        name: bound.BOUND[name][1] if name in bound.BOUND else value
        for name, value in vars(builtins).items()
    }


@pytest.mark.parametrize(
    "write",
    [
        lambda held: held.update({PROBE: 1}),
        lambda held: held.update([(PROBE, 1)]),
        lambda held: held.update(**{PROBE: 1}),
        lambda held: held.setdefault(PROBE, 1),
        lambda held: held.__ior__({PROBE: 1}),
        lambda held: held.__setitem__(PROBE, 1),
    ],
)
def test_a_write_reaches_builtins(live: LiveBuiltins, write: object) -> None:
    write(live)  # pyrefly: ignore[not-callable]

    assert vars(builtins)[PROBE] == 1
    assert live[PROBE] == 1


def test_setdefault_keeps_what_builtins_holds(live: LiveBuiltins) -> None:
    assert live.setdefault("len", 0) is bound.len
    assert live.setdefault("print", 0) is print
    assert builtins.len is bound.BOUND["len"][0]


def test_a_removal_reaches_builtins(live: LiveBuiltins) -> None:
    builtins._pyct_live_probe = 1  # pyrefly: ignore[missing-attribute]
    assert live.pop(PROBE) == 1
    assert PROBE not in vars(builtins)
    assert live.pop(PROBE, "gone") == "gone"
    with pytest.raises(KeyError):
        live.pop(PROBE)
    builtins._pyct_live_probe = 2  # pyrefly: ignore[missing-attribute]
    del live[PROBE]
    assert PROBE not in vars(builtins)


def test_every_read_sees_builtins_as_it_is_now(live: LiveBuiltins) -> None:
    builtins._pyct_live_probe = "late"  # pyrefly: ignore[missing-attribute]

    assert dict(live) == expected() == {**live}
    assert list(live) == list(vars(builtins)) == list(live.keys())
    assert dict(live.items()) == expected()
    assert list(live.values()) == list(expected().values())
    assert len(live) == len(vars(builtins))
    assert live == expected()
    assert (live != expected()) is False


def replaced(*args: object) -> None:
    """A `print` a target puts in `builtins` after its modules loaded."""


def test_a_copy_is_a_plain_dict_and_writes_nothing_back(
    live: LiveBuiltins, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builtins, "print", replaced)

    for made in (
        live.copy(),
        copy.copy(live),
        copy.deepcopy(live),
        pickle.loads(pickle.dumps(live)),
    ):
        assert type(made) is dict
        assert made["print"] is replaced and made["len"] is bound.len
    assert builtins.print is replaced


def test_popitem_and_clear_act_on_builtins() -> None:
    held = LiveBuiltins()
    real = vars(builtins)
    saved = real.copy()
    # nothing between the clear and the restore may look a builtin up: there are none
    real[PROBE] = 1
    popped = held.popitem()
    held.clear()
    emptied = not real
    real.update(saved)

    assert popped == (PROBE, 1)
    assert emptied
    assert len(held) == len(real)


def test_a_union_answers_as_on_builtins_own_dict(live: LiveBuiltins) -> None:
    assert (live | {PROBE: 1}) == {**expected(), PROBE: 1}
    assert ({PROBE: 1} | live) == {PROBE: 1, **expected()}
    with pytest.raises(TypeError):
        live | [(PROBE, 1)]  # pyrefly: ignore[unsupported-operation]
    assert LiveBuiltins.fromkeys([PROBE]) == {PROBE: None}
    assert PROBE not in vars(builtins)
    assert repr(live) == repr(expected())
    assert list(reversed(live)) == list(reversed(vars(builtins)))
