"""The constant each leaf of a path is declared as, and the sort that declares it."""

from pyct.solver.heads import SORTS


def leaf_symbol(name: str, index: int) -> str:
    """A leaf's symbol, written inside bars: ``arg.<name>`` for a name that is an identifier.

    The prefix keeps every symbol apart from the solver's own words, which
    a parameter may be named as, ``div`` say: cvc5 refuses to declare one,
    bars or not. Each character past ASCII is written as its UTF-8 bytes,
    ``%C3%A9`` for ``é``, so the program stays ASCII. Any other name is
    ``leaf.<n>``, n its position among the seed's leaves: a value inside an
    argument is named by its access, which holds brackets, quotes, and any
    character a key holds, ``|`` and the backslash among them, which not
    even a quoted symbol can.
    """
    if not name.isidentifier():
        return f"leaf.{index}"
    written = "".join(
        character if character.isascii() else "".join(f"%{byte:02X}" for byte in character.encode())
        for character in name
    )
    return f"arg.{written}"


def leaf_sort(name: str, kind: type) -> str:
    """The sort a leaf of that type is declared as; a type no sort holds is an error."""
    written = SORTS.get(kind)
    if written is None:
        raise ValueError(f"pyct cannot declare {name}: nothing solves a {kind.__name__} yet")
    return written
