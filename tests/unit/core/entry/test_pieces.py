"""The hooks around a piece of the target's code hand back what the code needs and record
nothing yet."""

from pyct.core.entry import substitutes
from pyct.core.entry.pieces import piece_in, piece_out, piece_over, piece_value

SITE = (3, 4, ("t", "xs"), ("t",))


def test_each_hook_hands_back_what_the_code_needs() -> None:
    iterable, value = [1, 2], object()

    assert piece_over(iterable, *SITE) is iterable
    assert piece_value(piece_in(*SITE), value) is value
    assert piece_out(*SITE) is None


def test_substituted_modules_import_the_hooks_from_substitutes() -> None:
    assert (substitutes.piece_over, substitutes.piece_in) == (piece_over, piece_in)
    assert (substitutes.piece_out, substitutes.piece_value) == (piece_out, piece_value)
